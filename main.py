from utils.runner import run, init_model
from utils.conversation import Conversation, Message
from utils.agent import Agent
from utils.preprompt import prepend
from helpers.file_utils import read_agents_from_file, read_lines_from_file
from typing import Tuple, Any, Optional

import requests
import transformers
import argparse
import os
os.environ["HF_MODULES_CACHE"] = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "modules")


import random
import psutil
from termcolor import colored
from functools import reduce
from transformers import AutoConfig, set_seed

try:
    import torch
    from auto_gptq import AutoGPTQForCausalLM
    from transformers import AutoTokenizer, TextGenerationPipeline
except ImportError:
    logger.warning('auto_gptq is unavailable, proceeding without gptq support.')
    torch = None
    AutoGPTQForCausalLM = None
    AutoTokenizer = None
    TextGenerationPipeline = None


def parse_args():
    parser = argparse.ArgumentParser(description='Process some model path.')
    parser.add_argument('--model_path', type=str, help='path to the model')
    parser.add_argument('--debug_template', type=str, help='init a conversation about chess')
    parser.add_argument('--conversation_settings', type=str, help='contains the setup for the conversation')
    parser.add_argument('--mode', type=str, help='choose a mode \(cpu, oobabooga, mpt\)')
    return parser.parse_args()

def _init_model(path: str, use_gptq=False, gptq_safetensors=False, verbose=False, **kwargs: Any) -> Any:
    if use_gptq:
        tokenizer = AutoTokenizer.from_pretrained(path, use_fast=False)
        model = AutoGPTQForCausalLM.from_quantized(
            path, device="cuda:0", safetensors=gptq_safetensors)
        return model, tokenizer
    else:
        return Llama(path, verbose=False, **kwargs)
    
def main():
    args = parse_args()
    model_path = args.model_path
#    model = init_model(model_path, n_threads=4, n_ctx=2048, use_mlock=False)
    
    
    if args.mode == "gpu":
        print("...mode: gpu -> run mainGPU.py instead")

    elif args.mode == "cpu":
        print("...mode: cpu")
        model = init_model(model_path, n_threads=psutil.cpu_count(logical=False) + 2, n_ctx=2048, use_mlock=False)    
    else:
        print("...mode: NO MODE GIVEN, QUITTING NOW")
        exit
    
    action_lines = read_lines_from_file("action_input.txt")
    
    conversation = Conversation()

    # --- EXPLANATION -------------------------------------------------
    # there are three options how to start the conversation
    # - on startup pass it a settings file with --conversation_settings <file>
    # - on startup pass it --debug_template, to have it talk about chess
    # - on startup don't pass anything, then the program will ask you to input persons by hand
    # --- EXPLANATION -------------------------------------------------
    if args.conversation_settings:
        agents, topic = read_agents_from_file(args.conversation_settings)
    elif args.debug_template:
        agents = [
            Agent(name='QuantumQuasar', self_description='I\'m a human, a master of quantum physics and a skilled ninja of the cosmos. I love exploring the mysteries of the universe and discovering new ways to bend the laws of physics to my will.', color='red'),
            Agent(name='RavenousReader', self_description='I devour books like a hungry dragon devours treasure. I\'m a human and always looking for my next literary adventure, and I love discussing my favorite stories with fellow bookworms.', color='green'),
            Agent(name='LunarLion', self_description='I\'m human, a nocturnal creature with a passion for the stars. When I\'m not admiring the night sky, you can find me exploring virtual worlds and battling foes with my trusty celestial claws.', color='blue')
        ]
        topic = 'chess openings'   
    else:
        topic = input(colored('Enter topic: ', 'cyan')).strip()
        agents = []

        # create a list of all available colors and shuffle it
        colors = ['red', 'green', 'yellow', 'blue', 'magenta']
        random.shuffle(colors)

        while True:
            name = input(colored('Enter agent name (or q to quit): ', 'cyan')).strip()
            if name == 'q':
                print('\n')
                break
            self_description = input(colored(f'Enter {name}\'s self description: ', 'cyan')).strip()
            # assign a color from the shuffled list to each agent
            color = colors.pop()
            agents.append(Agent(name=name, self_description=self_description, color=color))

    print(f"Agents: {agents}")
    print(f"Topic: {topic}")

    # --- EXPLANATION -------------------------------------------------
    # this part runs the conversation between the various ais
    # the whole behavior depends heavily on prompt handling here, if this is tweaked you may get other/better/worse outcome
    # note that additionally it will be important to have a model that fits to your prompts here. (ask in discord about more info about this)
    # --- EXPLANATION -------------------------------------------------
    first_time = True
    while True:
        for agent in agents:
            prompt = conversation.render_history()
            prompt = prepend(f'The topic seems to be {topic}', main_prompt=prompt)
            prompt = prepend(f'I\'m on a discord call with {", ".join([a.name for a in agents if a.name != agent.name])}', main_prompt=prompt)
            prompt = prepend(f'(Me, thinking to myself): I\'m {agent.name}, {agent.self_description}', main_prompt=prompt)
            if first_time:
                prompt = prepend('(Me, thinking to myself): I just met these people so I should probably take it slow', main_prompt=prompt)
                first_time = False

            stop_list = [f'{a.name}:' for a in agents]
            output = run(prompt=colored(f'{prompt}\nMe:', 'cyan'), model=model, stop=stop_list, name=agent.name, config=agent.config).replace('Me: ', '').strip().capitalize()
            output = reduce(lambda s, sub: s.replace(sub, ''), stop_list, output)

            # print('___' + prompt + '___')

            if output != '':
                message = Message(sender=agent.name, content=output)
                conversation.add_message(message)
                print(colored(f'{message.sender}: {message.content}', agent.color))
            else:
                random_action = random.choice(action_lines)
                message = Message(sender=agent.name, content=random_action)
                conversation.add_message(message)
                print(colored(f'{message.sender}: {message.content}', agent.color))
            


if __name__ == '__main__':
    main()