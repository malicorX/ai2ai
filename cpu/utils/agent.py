from dataclasses import dataclass
from typing import Dict
import random


class Agent:
    def __init__(self, name: str, color: str, self_description: str):
        self.name = name
        self.color = color
        self.self_description = self_description
        self.config = {
            'top_p': round(random.uniform(0.0, 0.65), 2),
            'top_k': random.randint(60, 32000),
            'temp': round(random.uniform(0.0, 0.65), 2),
            'repeat_penalty': round(random.uniform(1.0, 1.2), 2),
        }