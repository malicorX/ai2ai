import os
import sys
import json
import argparse

from colorama import Fore, Style, init

from gpu.characterAI import CharacterAI
from gpu.formatterAI import FormatterAI
from gpu.narratorAI import NarratorAI

init(autoreset=True)  # Automatically reset color back to default after print


def parse_args():
    parser = argparse.ArgumentParser(description='Process some model path.')
    parser.add_argument('--model_name', type=str, help='name of the model')
    return parser.parse_args()


def main():
    args = parse_args()
    model_name = args.model_name
    
    print("MODEL_NAME: " + model_name)

    narrator = NarratorAI("Narrator", "an AI designed to tell the story setting and environment", Fore.GREEN)
    formatter = FormatterAI("Formatter", "an AI designed to format responses.", Fore.LIGHTBLACK_EX)
    peter = CharacterAI("Peter", "a tennis professional from New York, 29 years old.", Fore.BLUE)
    mary = CharacterAI("Mary", "an environmentalist, passionate about climate change.", Fore.RED)

    conversation = """
A calm night in New York City.
"""

    characters = [narrator, peter, mary]
    i = 0
    while True:
        i += 1

        for character in characters:
            # --- EXPLANATION -------------------------------------------------
            # each character gets the following input (==longterm memory), which is used to generate his answer:
            # 
            # - conversation: this contains the complete conversation from everybody so far                                 TODO: take out all "thinks" here
            # - TODO: add stuff like google search / wolfram alpha and so on
            #
            # --- EXPLANATION -------------------------------------------------
            
            #print ("[ 1 ] conversation: " + conversation)
            character_prompt = character.create_prompt(conversation, 0.8)
            #print ("[ 2 ] character_prompt: " + character_prompt)
            character_response = character.generate_response(character_prompt, 0.8)
            
            if character_response:
                #print ("[ 3 ] character_response: " + character_response)

                formatter_prompt = formatter.create_prompt(character.name, character_response)
                #print ("[ 4 ] formatter_prompt: " + formatter_prompt)
                
                formatted_character_response = formatter.generate_response(formatter_prompt, 0.8)
                #print ("[ 5 ] formatted_character_response: " + formatted_character_response)
                
                conversation += formatted_character_response + "\n"
                #print ("[ 6 ] conversation (new): " + conversation)
                
                #print(character.color + formatted_character_response)
                break
            else:
                print("Error generating " + character.name + "'s response. Exiting.")
                return

        print(Fore.LIGHTBLACK_EX + conversation)

        if i == 5:
            break

if __name__ == '__main__':
    main()