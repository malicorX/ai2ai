from typing import List
from datetime import datetime


class Message:
    def __init__(self, sender: str, content: str):
        self.sender = sender
        self.content = content
        self.date = datetime.now()


class Conversation:
    def __init__(self, history: List[Message] = []):
        self.history = history

    def add_message(self, message: Message):
        self.history.append(message)

    def render_history(self) -> str:
        if not self.history:
            return ''
        sorted_history = sorted(self.history, key=lambda x: x.date)
        rendered_history = ""
        for message in sorted_history:
            rendered_history += f"{message.sender}: {message.content}\n"
        return rendered_history