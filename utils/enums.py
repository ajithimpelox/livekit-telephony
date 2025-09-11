from enum import Enum


class ChatType(str, Enum):
    normal = "normal"
    system = "system"
    error = "error"
