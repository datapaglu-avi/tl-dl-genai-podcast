# This file to convert audio to video

from moviepy import AudioFileClip, ImageClip

# Paths
audio_path = "podcast.mp3"
image_path = "TL_DL.png"
output_path = "podcast_video.mp4"

# Load audio and image
audio = AudioFileClip(audio_path)
image = ImageClip(image_path)

video_clip = image.with_audio(audio)
video_clip.duration = audio.duration
video_clip.fps = 24

# Export final video
video_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
