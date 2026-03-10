import queue
from threading import Lock


class AudioPriorityQueue:
    HOLE_DETECTION = 1
    AIR_OBSTACLE = 2
    VOICE_MENU = 3
    OBJECT_DETECTION = 4
    TEXT_RECOGNITION = 4
    GPS_NAVIGATION = 5

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
