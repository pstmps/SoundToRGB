
#       Extract dominant frequency from audio and convert to rgb and display it
#       Copyright (C) 2023  Michael-Philipp Stiebing mstiebing <at> gmail.com
#
#       This program is free software: you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation, either version 3 of the License, or
#       (at your option) any later version.
#
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#
#       You should have received a copy of the GNU General Public License
#       along with this program.  If not, see <http://www.gnu.org/licenses/>.


import pyaudio
import numpy as np
import struct
import wx
from collections import deque

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

FRAMES_PER_BUFFER = 2048

# Smoothing parameters
# higher values, less responsive, slower update
# lower values, noise influences the color to a higher degree
RGB_SMOOTH = 3     # amount of rgb samples averaged
RMS_SMOOTH = 3
BUFFER_SIZE = 12    # size of circular buffer of audio samples
TIMER_DELAY = 40   # timer for GUI update

RMS_DIV = 1000

# hz ranges, specific to microphone performance, the value will be clamped to this range
MIN_HZ = 300
#MIN_HZ = 440
MAX_HZ = 4000
#MAX_HZ = 1760

# set frequency offset (for aesthetic reasons or to offset microphone performance)
FREQ_OFFSET = 0

#MAX_HZ += 100

# range of color wavelengths
MIN_NM = 380
MAX_NM = 780

# function wouldnt work if these vallues are out of range
if (MIN_NM < 380):
    MIN_NM = 380
if (MAX_NM > 780):
    MAX_NM = 780

def convert_nm_to_rgb(w):
    gamma = 0.80

    w = round(w)

    if (w >= 380 and w < 440):
        red = -(w - 440) / (440 - 380)
        green = 0.0
        blue = 1.0
    elif (w >= 440 and w < 490):
        red = 0.0
        green = (w - 440) / (490 - 440)
        blue = 1.0
    elif (w >= 490 and w < 510):
        red = 0.0
        green = 1.0
        blue = -(w - 510) / (510 - 490)
    elif (w >= 510 and w < 580):
        red = (w - 510) / (580 - 510)
        green = 1.0
        blue = 0.0
    elif (w >= 580 and w < 645):
        red = 1.0
        green = -(w - 645) / (645 - 580)
        blue = 0.0
    elif (w >= 645 and w < 781):
        red = 1.0
        green = 0.0
        blue = 0.0
    else:
        red = 1.0
        green = 1.0
        blue = 1.0

    if (w >= 380 and w < 420):
        factor = 0.3 + 0.7 * (w - 380) / (420 - 380)
    elif (w >= 420 and w < 701):
        factor = 1.0
    elif (w >= 701 and w < 781):
        factor = 0.3 + 0.7 * (780 - w) / (780 - 700)
    else:
        factor = 1.0

    R = 255 * (red * factor) ** gamma if red > 0 else 0
    G = 255 * (green * factor) ** gamma if green > 0 else 0
    B = 255 * (blue * factor) ** gamma if blue > 0 else 0

    R = round(R)
    G = round(G)
    B = round(B)

    #R = hex(int(R))
    #G = hex(int(G))
    #B = hex(int(B))

    return R,G,B

def clamp_number(num, a, b):
  return max(min(num, max(a, b)), min(a, b))

def translate(value, leftMin, leftMax, rightMin, rightMax):

    leftSpan = leftMax - leftMin
    rightSpan = rightMax - rightMin

    valueScaled = float(value - leftMin) / float(leftSpan)

    return rightMin + (valueScaled * rightSpan)

def extract_peak_frequency(data, sampling_rate):
    fft_data = np.fft.fft(data)
    freqs = np.fft.fftfreq(len(data))

    peak_coefficient = np.argmax(np.abs(fft_data))
    peak_freq = freqs[peak_coefficient]

    return abs(peak_freq * sampling_rate)

class MyFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Audio IN color OUT")
        self.SetBackgroundColour(wx.Colour(0, 0, 0)) # set initial background color
        self.Bind(wx.EVT_PAINT, self.on_paint) # bind paint event to on_paint method
        self.timer = wx.Timer(self) # create timer object
        self.Bind(wx.EVT_TIMER, self.update_color, self.timer) # bind timer event to update_color method
        self.timer.Start(TIMER_DELAY) # start the timer to update color every 100 milliseconds
        self.Bind(wx.EVT_KEY_DOWN, self.onKey)

        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            output=False,
            frames_per_buffer=FRAMES_PER_BUFFER,
        )  # create audio stream

        self.rgb_values = []  # list to store RGB values from previous frames
        self.rms_values = []  # list to store RMS values from previous frames
        self.freq_buffer = deque(maxlen=BUFFER_SIZE)

#       uncomment the line below to start in fullscreen mode (exit with escape)
#        self.ShowFullScreen(True)

    def onKey(self, event):

        key_code = event.GetKeyCode()
        if key_code == wx.WXK_ESCAPE:
            self.Close()
        else:
            event.Skip()

    def on_paint(self, event):
        dc = wx.PaintDC(self) # create a device context to draw on the window
        dc.Clear() # clear the device context

    def update_color(self, event):

        wf_data = self.stream.read(FRAMES_PER_BUFFER)  # read audio sample from input
        wf_data = struct.unpack(str(FRAMES_PER_BUFFER) + 'h', wf_data)
        wf_data = np.array(wf_data)

        freq = extract_peak_frequency(wf_data, RATE)  # extract dominant frequency from audio sample
        rms = np.sqrt(np.mean(np.absolute(wf_data) ** 2))
        self.freq_buffer.append(freq)

        # compute average frequency over buffer
        freqs = np.array(self.freq_buffer)
        avg_freq = np.mean(freqs)
        avg_freq = clamp_number(avg_freq,MIN_HZ,MAX_HZ) + FREQ_OFFSET
        nm = translate(avg_freq, MIN_HZ, MAX_HZ, MAX_NM, MIN_NM)  # convert frequency to wavelength (high freq -> low wavelength)
        r, g, b = convert_nm_to_rgb(nm)  # convert wavelength to RGB values

        self.rgb_values.append((r, g, b))
        if len(self.rgb_values) > RGB_SMOOTH:
            # remove the oldest RGB value if the list is longer than 10
            self.rgb_values.pop(0)
        # compute the average RGB values across the previous frames
        avg_r = sum([rgb[0] for rgb in self.rgb_values]) / len(self.rgb_values)
        avg_g = sum([rgb[1] for rgb in self.rgb_values]) / len(self.rgb_values)
        avg_b = sum([rgb[2] for rgb in self.rgb_values]) / len(self.rgb_values)

        print("Frequency: " + str(round(avg_freq,2)) + " hz \t Wavelength: " + str(round(nm,2)) + " nm \tR: " + str(avg_r) + "\tG: " + str(avg_g) + "\tB: " + str(avg_b))
        print("RMS " + str(rms))

        self.rms_values.append((rms))
        if len(self.rms_values) > RMS_SMOOTH:
            # remove the oldest RGB value if the list is longer than 10
            self.rms_values.pop(0)
        # compute the average RGB values across the previous frames
        avg_rms = sum([rms for rms in self.rms_values]) / len(self.rms_values)

        print("RMS " + str(rms / RMS_DIV))
        print("RMS " + str(avg_rms / RMS_DIV))
        avg_rms = avg_rms / RMS_DIV

        avg_r = avg_r + (avg_r * avg_rms)
        avg_g = avg_g + (avg_g * avg_rms)
        avg_b = avg_b + (avg_b * avg_rms)
        # set the background color using the generated RGB values
        self.SetBackgroundColour(wx.Colour(avg_r, avg_g, avg_b))
        # refresh the window to update the background color
        self.Refresh()


if __name__ == "__main__":
    app = wx.App()
    frame = MyFrame()
    frame.Show()
    app.MainLoop()


