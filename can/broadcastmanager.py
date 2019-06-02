# coding: utf-8

"""
Exposes several methods for transmitting cyclic messages.

The main entry point to these classes should be through
:meth:`can.BusABC.send_periodic`.
"""

import abc
import logging
import threading
import time
import can

log = logging.getLogger("can.bcm")


class CyclicTask:
    """
    Abstract Base for all cyclic tasks.
    """

    @abc.abstractmethod
    def stop(self):
        """Cancel this periodic task.

        :raises can.CanError:
            If stop is called on an already stopped task.
        """


class CyclicSendTaskABC(CyclicTask):
    """
    Message send task with defined period
    """

    def __init__(self, messages, period):
        """
        :param List[can.Message] messages: The message to be sent periodically.
        :param float period: The rate in seconds at which to send the messages.
        """
        if not isinstance(messages, list):
            if isinstance(messages, can.Message):
                messages = [messages]
            else:
                raise ValueError("Must be either a list or a Message")
        if not messages:
            raise ValueError("Must be at least a list of length 1")

        self.messages = messages

        all_same_id = all(
            message.arbitration_id == messages[0].arbitration_id for message in messages
        )
        if not all_same_id:
            raise ValueError("All Arbitration IDs should be the same")

        # Take the Arbitration ID of the first element
        self.can_id = messages[0].arbitration_id
        self.arbitration_id = messages[0].arbitration_id
        self.period = period


class LimitedDurationCyclicSendTaskABC(CyclicSendTaskABC):
    def __init__(self, messages, period, duration):
        """Message send task with a defined duration and period.

        :param List[can.Message] messages: The message to be sent periodically.
        :param float period: The rate in seconds at which to send the messages.
        :param float duration:
            The duration to keep sending this messages at given rate.
        """
        super().__init__(messages, period)
        self.duration = duration


class RestartableCyclicTaskABC(CyclicSendTaskABC):
    """Adds support for restarting a stopped cyclic task"""

    @abc.abstractmethod
    def start(self):
        """Restart a stopped periodic task.
        """


class ModifiableCyclicTaskABC(CyclicSendTaskABC):
    """Adds support for modifying a periodic message"""

    def modify_data(self, messages):
        """Update the contents of this periodically sent messages without altering
        the timing.

        :param List[can.Message] messages:
          The message with the new :attr:`can.Message.data`.
          Note: The arbitration ID cannot be changed.
        """
        self.messages = messages


class MultiRateCyclicSendTaskABC(CyclicSendTaskABC):
    """A Cyclic send task that supports switches send frequency after a set time.
    """

    def __init__(self, channel, messages, count, initial_period, subsequent_period):
        """
        Transmits a message `count` times at `initial_period` then continues to
        transmit messages at `subsequent_period`.

        :param channel: See interface specific documentation.
        :param List[can.Message] messages:
        :param int count:
        :param float initial_period:
        :param float subsequent_period:
        """
        super().__init__(channel, messages, subsequent_period)


class ThreadBasedCyclicSendTask(
    ModifiableCyclicTaskABC, LimitedDurationCyclicSendTaskABC, RestartableCyclicTaskABC
):
    """Fallback cyclic send task using thread."""

    def __init__(self, bus, lock, messages, period, duration=None):
        super().__init__(messages, period, duration)
        self.bus = bus
        self.lock = lock
        self.stopped = True
        self.thread = None
        self.end_time = time.time() + duration if duration else None
        self.start()

    def stop(self):
        self.stopped = True

    def start(self):
        self.stopped = False
        if self.thread is None or not self.thread.is_alive():
            name = "Cyclic send task for 0x%X" % (self.messages[0].arbitration_id)
            self.thread = threading.Thread(target=self._run, name=name)
            self.thread.daemon = True
            self.thread.start()

    def _run(self):
        msg_index = 0
        while not self.stopped:
            # Prevent calling bus.send from multiple threads
            with self.lock:
                started = time.time()
                try:
                    self.bus.send(self.messages[msg_index])
                    msg_index = (msg_index + 1) % len(self.messages)
                except Exception as exc:
                    log.exception(exc)
                    break
            if self.end_time is not None and time.time() >= self.end_time:
                break
            # Compensate for the time it takes to send the message
            delay = self.period - (time.time() - started)
            time.sleep(max(0.0, delay))
