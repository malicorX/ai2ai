import requests

HOST = 'localhost:5000'
URI = f'http://{HOST}/api/v1/generate'

from colorama import Fore

class FormatterAI():
    def __init__(self, name, description, color):
        self.name = name
        self.description = description
        self.color = color

        
    def create_prompt(self, name, response):
        prompt = f"""
### FORMATTING TASK:
You are tasked with formatting the following response from {name} into a narrative format. The response can either be thought, said, or acted by {name}. Choose the most appropriate format.

### RESPONSE TO FORMAT:
{response}

### YOUR FORMATTED RESPONSE:
"""
        return prompt

    def generate_response(self, prompt, top_p):
        request = {
            'prompt': prompt,
            'max_new_tokens': 150,
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
