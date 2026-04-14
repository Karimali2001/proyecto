import queue
from threading import Lock
import time


class AudioPriorityQueue:
    HOLE_DETECTION = 1
    SEMAPHORE = 2
    # AIR_OBSTACLE 
    VOICE_MENU = 3
    OBJECT_DETECTION = 4
    TEXT_RECOGNITION = 4
    NAVIGATION = 5

    def __init__(self, audio_interface):
        """
        Initializes the priority queue with an audio interface.

        Args:
            audio_interface: The UI audio interface used to process audio tasks.

        Attributes:
            pq (queue.PriorityQueue): The internal priority queue for managing tasks.
            audio_interface: Stores the provided audio interface instance.
            current_priority (float): Tracks the priority of the currently processed task.
                Initialized to float('inf') to indicate that no task is currently being processed,
                and any incoming task will have a lower (higher priority) value.
            lock (Lock): Ensures thread-safe operations on the queue.
            counter (int): Used to preserve FIFO order for tasks with the same priority.
        """
        self.pq = queue.PriorityQueue()
        self.audio_interface = audio_interface
        self.current_priority = float("inf")
        self.lock = Lock()
        self.counter = 0  # To preserve FIFO for same priority

    def play_concurrent(self, message):
        """
        Plays sounds or short voice messages immediately without queuing.
        """
        if isinstance(message, dict):
            action = message.get("action")
            
            if action == "sound":
                sound_type = message.get("sound_type")
                position = message.get("position")
                
                if not sound_type or not position:
                    return
                    
                self.audio_interface.play_spatial_sound(
                    position=position,
                    sound_type=sound_type
                )
                
            elif action == "fast_voice":
                text = message.get("text")
                
                if not text:
                    return
                    
                self.audio_interface.speak_fast_background(text)

    def put(self, priority, message):
        """
        Lower number means higher priority (e.g., 1 is higher than 5).
        """
        with self.lock:
            # If the new message has higher priority than the currently playing one, stop current
            if priority < self.current_priority:
                print(
                    f"[PriorityQueue] Preempting current audio for higher priority: {priority}"
                )
                self.audio_interface.stop()

            self.pq.put((priority, self.counter, message))
            self.counter += 1

    def get(self):
        priority, _, message = self.pq.get()
        with self.lock:
            self.current_priority = priority
        return priority, message

    def task_done(self):
        with self.lock:
            self.current_priority = float("inf")
        self.pq.task_done()

    def is_priority_active_or_queued(self, target_priority):
        """
        Returns True if the specified priority is currently playing OR waiting in the queue.
        """
        with self.lock:
            if self.current_priority == target_priority:
                return True

            # Check the pending queue (pq.queue is a list of tuples: (priority, counter, message))
            for item in self.pq.queue:
                if item[0] == target_priority:
                    return True

            return False

    def wait_for_priority(self, target_priority):
        """
        Blocks until there are no active or queued tasks of the specified priority.

        """
        # We check in a loop with a small sleep to avoid busy waiting, since the queue doesn't provide a direct way to wait for a specific priority to clear.
        while self.is_priority_active_or_queued(target_priority):
            time.sleep(0.05)
