import queue
from threading import Lock


class AudioPriorityQueue:
    HOLE_DETECTION = 1
    DANGEROUS_OBJECTS = 2
    AIR_OBSTACLE = 3
    VOICE_MENU = 4
    OBJECT_DETECTION = 5
    TEXT_RECOGNITION = 5
    NAVIGATION = 6

    def __init__(self, audio_driver):
        """
        Initializes the priority queue with an audio driver.

        Args:
            audio_driver: The audio driver instance to be used for processing audio tasks.

        Attributes:
            pq (queue.PriorityQueue): The internal priority queue for managing tasks.
            audio_driver: Stores the provided audio driver instance.
            current_priority (float): Tracks the priority of the currently processed task.
                Initialized to float('inf') to indicate that no task is currently being processed,
                and any incoming task will have a lower (higher priority) value.
            lock (Lock): Ensures thread-safe operations on the queue.
            counter (int): Used to preserve FIFO order for tasks with the same priority.
        """
        self.pq = queue.PriorityQueue()
        self.audio_driver = audio_driver
        self.current_priority = float("inf")
        self.lock = Lock()
        self.counter = 0  # To preserve FIFO for same priority

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
                self.audio_driver.stop()

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
