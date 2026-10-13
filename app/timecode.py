"""Time input shared by the player controls and regression tests."""
import re


def parse_timecode(text, duration):
    text = text.strip()
    if not re.fullmatch(r"[0-9]+(?::[0-9]{1,2}){0,2}", text):
        raise ValueError("请输入秒数、分:秒或时:分:秒")
    parts = [int(part) for part in text.split(":")]
    if any(part >= 60 for part in parts[1:]):
        raise ValueError("冒号后的分、秒必须小于60")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    if duration <= 0:
        raise ValueError("视频时长未知，暂时无法跳转")
    if seconds > duration:
        raise ValueError("输入时间不能超过视频时长")
    return float(seconds)


def format_timecode(seconds):
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
