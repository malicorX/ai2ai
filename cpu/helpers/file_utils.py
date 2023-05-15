from utils.agent import Agent

def read_agents_from_file(filename):
    agents = []
    topic = None
    with open(filename, 'r') as file:
        lines = file.readlines()
        for line in lines:
            if line.strip():
                if topic is None:
                    topic = line.strip()
                else:
                    name, self_description, color = line.strip().split(';')
                    agent = Agent(name=name, self_description=self_description, color=color)
                    agents.append(agent)
    return agents, topic
    
def read_lines_from_file(filename):
    with open(filename, 'r') as file:
        lines = file.readlines()
    return [line.strip() for line in lines if line.strip()]    