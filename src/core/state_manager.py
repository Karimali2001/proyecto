

class StateManager:

    #enum
    BOOTING = 0
    RUNNING = 1
    THROTTLING = 2
    SHUTTING_DOWN = 3
    
    def __init__(self):
        self.state = StateManager.BOOTING

    def update(self):
        
