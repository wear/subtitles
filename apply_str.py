from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.audio.io.AudioFileClip import AudioFileClip

generator = lambda txt: TextClip(txt, font='Georgia-Regular',
                                fontsize=24, color='black')
subtitles = SubtitlesClip("test.srt", generator)
myvideo = VideoFileClip("test.mp4")

final = CompositeVideoClip([myvideo, subtitles.set_pos('bottom','center')])
final.set_audio(AudioFileClip("test.wav"))
final.to_videofile("final.avi", fps=myvideo.fps, codec="mpeg4")