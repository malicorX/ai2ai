import os
import sys
import json
import requests
from colorama import Fore, Style, init

init(autoreset=True)  # Automatically reset color back to default after print

HOST = 'localhost:5000'
URI = f'http://{HOST}/api/v1/generate'


class Character:
    def __init__(self, name, description):
        self.name = name
        self.description = description

    def create_prompt(self, conversation, top_p):
        prompt = f"""
### YOUR CHARACTER:
You are {self.name}, {self.description}.

### YOUR CONVERSATION SO FAR:{conversation}

### YOUR RESPONSE:
"""
        return prompt

    def generate_response(self, prompt, top_p):
        request = {
            'prompt': prompt,
            'max_new_tokens': 1500,
            'do_sample': True,
            'temperature': 1.3,
            'top_p': top_p,
            'typical_p': 1,
            'repetition_penalty': 1.18,
            'top_k': 40,
            'min_length': 0,
            'no_repeat_ngram_size': 0,
            'num_beams': 1,
            'penalty_alpha': 0,
            'length_penalty': 1,
            'early_stopping': False,
            'seed': -1,
            'add_bos_token': True,
            'truncation_length': 2048,
            'ban_eos_token': False,
            'skip_special_tokens': True,
            'stopping_strings': []
        }

        response = requests.post(URI, json=request)

        if response.status_code == 200:
            result = response.json()['results'][0]['text']
            response_text = result.split("### YOUR RESPONSE:")[-1].strip()
            return response_text
        else:
            return None


class FormatterAI(Character):
    def __init__(self):
        super().__init__("Formatter", "an AI designed to format responses.")
        
    def create_prompt(self, name, response):
        prompt = f"""
### FORMATTING TASK:
You are tasked with formatting the following response from {name} into a narrative format. The response can either be thought, said, or acted by {name}. Choose the most appropriate format.

### RESPONSE TO FORMAT:
{response}

### YOUR FORMATTED RESPONSE:
"""
        return prompt


def main():
    peter = Character("Peter", "a tennis professional from New York, 29 years old.")
    mary = Character("Mary", "an environmentalist, passionate about climate change.")
    formatter = FormatterAI()

    conversation = """
### YOUR CONVERSATION SO FAR:
Peter sits down at the bar on an empty stool next to Mary.
(THINKING) Peter: She looks really pretty.
Peter says to Mary: Hey there. How are you?
"""

    i = 0
    while True:
        i += 1

        peter_prompt = peter.create_prompt(conversation, 0.8)
        peter_response = peter.generate_response(peter_prompt, 0.8)
        
        if peter_response:
            formatter_prompt = formatter.create_prompt(peter.name, peter_response)
            formatted_peter_response = formatter.generate_response(formatter_prompt, 0.8)
            conversation += formatted_peter_response + "\n"
            print(Fore.BLUE + formatted_peter_response)
        else:
            print("Error generating Peter's response. Exiting.")
            break

        mary_prompt = mary.create_prompt(conversation, 0.8)
        mary_response = mary.generate_response(mary_prompt, 0.8)
        
        if mary_response:
            formatter_prompt = formatter.create_prompt(mary.name, mary_response)
            formatted_mary_response = formatter.generate_response(formatter_prompt, 0.8)
            conversation += formatted_mary_response + "\n"
            print(Fore.RED + formatted_mary_response)
        else:
            print("Error generating Mary's response. Exiting.")
            break

        print(Fore.LIGHTBLACK_EX + conversation)
        
        if i == 4:
            break

if __name__ == '__main__':
    main()