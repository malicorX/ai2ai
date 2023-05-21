import requests
import json

from gpu.formatterAI import FormatterAI

HOST = 'localhost:5000'
URI = f'http://{HOST}/api/v1/generate'

from colorama import Fore

class CharacterAI:
    def __init__(self, name, description, conversation, color):
        self.name = name
        self.description = description
        self.color = color
        self.conversation = conversation



    def act(self, i):
        formatter = FormatterAI("Formatter", "an AI designed to format responses.", Fore.LIGHTBLACK_EX)

        character_prompt = self.create_prompt()
        print ("[ " + str(i) +  "-2 ] character_prompt: " + character_prompt)
        character_response = self.generate_response(character_prompt)
        
        if character_response:
            print ("[ " + str(i) +  "-3 ] character_response: " + character_response)

            formatter_prompt = formatter.create_prompt(self.name, character_response)
            print ("[ " + str(i) +  "-4 ] formatter_prompt: " + formatter_prompt)
            
            formatted_character_response = formatter.generate_response(formatter_prompt, 0.8)
            print ("[ " + str(i) +  "-5 ] formatted_character_response: " + formatted_character_response)
            
            self.conversation += formatted_character_response + "\n"
            print ("[ " + str(i) +  "-6 ] conversation (new): " + self.conversation)
            
            print(self.color + formatted_character_response)
            
        else:
            print("Error generating " + self.name + "'s response. Exiting.")
            return
    

    def create_prompt(self):
        __DEBUG__ = False
   
        prompt = f"""
### YOUR CHARACTER:
You are {self.name}, {self.description}.

### CONVERSATION SO FAR:{self.conversation}

### YOUR RESPONSE:
"""

        if (__DEBUG__):
            print (" === ___DEBUG___ = BEGIN ==============================================")
            print ("name: " + self.name)
            print ("description: " + self.description)
            print ("conversation: " + self.conversation)
            print ("prompt: " + prompt)
            print (" === ___DEBUG___ = BEGIN ==============================================")
            
        return prompt

    def generate_response(self, prompt):
        __DEBUG__ = False

        top_p = 0.8

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

        if (__DEBUG__):
            print (" === ___DEBUG___ = BEGIN ==============================================")
            print ("name: " + self.name)
            print ("prompt: " + prompt)
            print ("request: " + json.dumps(request))
            print ("response: " + json.dumps(response.json()))
            print (" === ___DEBUG___ = END   ==============================================")

        if response.status_code == 200:
            result = response.json()['results'][0]['text']
            response_text = result.split("### YOUR RESPONSE:")[-1].strip()
            return response_text
        else:
            print(Fore.RED + "ERROR!!! " + str(response.status_code))
            return None

