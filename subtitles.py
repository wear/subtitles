import argparse
import speech_recognition as sr
import audioop
import os
import io
import wave
import math
import multiprocessing
import subprocess
import sys
import tempfile
from progressbar import ProgressBar, Percentage, Bar, ETA
from formatters import srt_formatter


def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None

def extract_audio(filename, channels=1, rate=16000):
    temp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    if not os.path.isfile(filename):
        print "The given file does not exist: {0}".format(filename)
        raise Exception("Invalid filepath: {0}".format(filename))
    if not which("ffmpeg"):
        print "ffmpeg: Executable not found on machine."
        raise Exception("Dependency not found: ffmpeg")
    command = ["ffmpeg", "-y", "-i", filename, "-ac", str(channels), "-ar", str(rate), "-loglevel", "error", temp.name]
    use_shell = True if os.name == "nt" else False
    subprocess.check_output(command, stdin=open(os.devnull), shell=use_shell)
    return temp.name, rate

class SpeechRecognizer(object):
    def __init__(self, rate=44100):
        self.rate = rate

    def __call__(self, file):
        try:
          r = sr.Recognizer()
          with sr.AudioFile(file) as source:
              audio = r.record(source)  # read the entire audio file

          try:
              # for testing purposes, we're just using the default API key
              # to use another API key, use `r.recognize_google(audio, key="GOOGLE_SPEECH_RECOGNITION_API_KEY")`
              # instead of `r.recognize_google(audio)`
              return r.recognize_google(audio)
              os.remove(file)
          except sr.UnknownValueError:
              print("Google Speech Recognition could not understand audio, {file}".format(file=file))
          except sr.RequestError as e:
              print("Could not request results from Google Speech Recognition service; {0}".format(e))

        except KeyboardInterrupt:
            return

def percentile(arr, percent):
    arr = sorted(arr)
    k = (len(arr) - 1) * percent
    f = math.floor(k)
    c = math.ceil(k)
    if f == c: return arr[int(k)]
    d0 = arr[int(f)] * (c - k)
    d1 = arr[int(c)] * (k - f)
    return d0 + d1

def find_speech_regions(filename, frame_width=4096, min_region_size=0.5, max_region_size=6):
    reader = wave.open(filename)
    sample_width = reader.getsampwidth()
    rate = reader.getframerate()
    n_channels = reader.getnchannels()
    chunk_duration = float(frame_width) / rate

    n_chunks = int(math.ceil(reader.getnframes()*1.0 / frame_width))
    energies = []

    for i in range(n_chunks):
        chunk = reader.readframes(frame_width)
        energies.append(audioop.rms(chunk, sample_width * n_channels))

    threshold = percentile(energies, 0.2)

    elapsed_time = 0

    regions = []
    region_start = None

    for energy in energies:
        is_silence = energy <= threshold
        max_exceeded = region_start and elapsed_time - region_start >= max_region_size

        if (max_exceeded or is_silence) and region_start:
            if elapsed_time - region_start >= min_region_size:
                regions.append((region_start, elapsed_time))
                region_start = None

        elif (not region_start) and (not is_silence):
            region_start = elapsed_time
        elapsed_time += chunk_duration
    return regions

class FLACConverter(object):
    def __init__(self, source_path, include_before=0.25, include_after=0.25):
        self.source_path = source_path
        self.include_before = include_before
        self.include_after = include_after

    def __call__(self, region):
        try:
            start, end = region
            start = max(0, start - self.include_before)
            end += self.include_after
            temp = tempfile.NamedTemporaryFile(suffix='.flac', delete=False)
            command = ["ffmpeg","-ss", str(start), "-t", str(end - start),
                       "-y", "-i", self.source_path,
                       "-loglevel", "error", temp.name]
            use_shell = True if os.name == "nt" else False
            subprocess.check_output(command, stdin=open(os.devnull), shell=use_shell)
            return temp.name

        except KeyboardInterrupt:
            return

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('source_path', help="Path to the video or audio file to subtitle", nargs='?')

  args = parser.parse_args()

  if not args.source_path:
      print("Error: You need to specify a source path.")
      return 1

  audio_filename, audio_rate = extract_audio(args.source_path)

  regions = find_speech_regions(args.source_path)
  pool = multiprocessing.Pool(5)

  converter = FLACConverter(source_path = audio_filename)
  recognizer = SpeechRecognizer(rate=audio_rate)

  transcripts = []
  if regions:
      try:
        widgets = ["Converting speech regions to FLAC files: ", Percentage(), ' ', Bar(), ' ', ETA()]
        pbar = ProgressBar(widgets=widgets, maxval=len(regions)).start()
        extracted_regions = []
        for i, extracted_region in enumerate(pool.imap(converter, regions)):
            extracted_regions.append(extracted_region)
            pbar.update(i)
        pbar.finish()

        widgets = ["Performing speech recognition: ", Percentage(), ' ', Bar(), ' ', ETA()]
        pbar = ProgressBar(widgets=widgets, maxval=len(regions)).start()

        for i, transcript in enumerate(pool.imap(recognizer, extracted_regions)):
            transcripts.append(transcript)
            pbar.update(i)
        pbar.finish()

      except KeyboardInterrupt:
          pbar.finish()
          pool.terminate()
          pool.join()
          print "Cancelling transcription"

  timed_subtitles = [(r, t) for r, t in zip(regions, transcripts) if t]
  formatted_subtitles = srt_formatter(timed_subtitles)
  base, ext = os.path.splitext(args.source_path)
  dest = "assets/{base}.{format}".format(base=base, format='srt')

  with open(dest, 'wb') as f:
    f.write(formatted_subtitles.encode("utf-8"))
  os.remove(audio_filename)

  return 0

if __name__ == '__main__':
    sys.exit(main())