from gpu.character import Character
from colorama import Fore

class NarratorAI(Character):
    def __init__(self):
        super().__init__("Narrator", "an AI designed to tell the story setting and environment", Fore.GREEN)
        
    def create_prompt(self, name, response):
        prompt = f"""
### FORMATTING TASK:
You are tasked with telling the story environment and setting, where people are and what they plan to do.

### RESPONSE TO FORMAT:
{response}

### YOUR FORMATTED RESPONSE:
"""
        return prompt
