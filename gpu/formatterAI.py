from gpu.character import Character
from colorama import Fore

class FormatterAI(Character):
    def __init__(self):
        super().__init__("Formatter", "an AI designed to format responses.", Fore.LIGHTBLACK_EX)
        
    def create_prompt(self, name, response):
        prompt = f"""
### FORMATTING TASK:
You are tasked with formatting the following response from {name} into a narrative format. The response can either be thought, said, or acted by {name}. Choose the most appropriate format.

### RESPONSE TO FORMAT:
{response}

### YOUR FORMATTED RESPONSE:
"""
        return prompt
