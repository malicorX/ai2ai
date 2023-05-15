def prepend(pre_prompt, main_prompt, newline=True) -> str:
    if pre_prompt[-2:] == '\n' or newline == False:
        return pre_prompt + main_prompt
    else:
        return pre_prompt + '\n' + main_prompt
