"""转换预设：定义不同平台的目标体积、尺寸、帧率与回退梯度。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str            # 显示名
    max_bytes: int       # 体积上限（字节）
    max_edge: int        # 起始最大边（像素）
    fps: int             # 起始帧率
    suffix: str          # 输出文件名后缀
    edge_ladder: tuple   # 分辨率回退梯度（从大到小）
    fps_ladder: tuple    # 帧率回退梯度（从大到小）


PRESETS = {
    "qq": Preset(
        name="QQ",
        max_bytes=5 * 1024 * 1024,
        max_edge=480,
        fps=15,
        suffix="_qq",
        edge_ladder=(480, 400, 320, 256),
        fps_ladder=(15, 12, 10),
    ),
    "wechat": Preset(
        name="微信表情",
        max_bytes=1 * 1024 * 1024,
        max_edge=300,
        fps=12,
        suffix="_wechat",
        edge_ladder=(300, 256, 200, 160),
        fps_ladder=(12, 10, 8),
    ),
}


def get_preset(key: str) -> Preset:
    """按 key 取预设，未知 key 抛 KeyError。"""
    return PRESETS[key]
