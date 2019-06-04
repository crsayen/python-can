"""
This module tests multiple message cyclic send tasks.
"""
import unittest

import time
import can

from .config import TEST_INTERFACE_SOCKETCAN

@unittest.skipUnless(TEST_INTERFACE_SOCKETCAN, "skip testing of socketcan")
class SocketCanCyclicMultiple(unittest.TestCase):
    BITRATE = 500000
    TIMEOUT = 0.1

    INTERFACE_1 = "virtual"
    CHANNEL_1 = "vcan0"
    INTERFACE_2 = "virtual"
    CHANNEL_2 = "vcan0"

    PERIOD = 1.0
    TIMEOUT = 1.0

    def _find_start_index(self, tx_messages, message):
        """
        :param tx_messages:
            The list of messages that were passed to the periodic backend
        :param message:
            The message whose data we wish to match and align to

        :returns: start index in the tx_messages
        """
        start_index = -1
        for index, tx_message in enumerate(tx_messages):
            if tx_message.data == message.data:
                start_index = index
                break
        return start_index

    def setUp(self):
        self._send_bus = can.Bus(
            interface=self.INTERFACE_1, channel=self.CHANNEL_1, bitrate=self.BITRATE
        )
        self._recv_bus = can.Bus(
            interface=self.INTERFACE_2, channel=self.CHANNEL_2, bitrate=self.BITRATE
        )

    def tearDown(self):
        self._send_bus.shutdown()
        self._recv_bus.shutdown()

    def test_cyclic_multiple_even(self):
        messages = []
        messages.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x11, 0x11, 0x11, 0x11, 0x11, 0x11],
                is_extended_id=False,
            )
        )
        messages.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x22, 0x22, 0x22, 0x22, 0x22, 0x22],
                is_extended_id=False,
            )
        )
        messages.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x33, 0x33, 0x33, 0x33, 0x33, 0x33],
                is_extended_id=False,
            )
        )
        messages.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x44, 0x44, 0x44, 0x44, 0x44, 0x44],
                is_extended_id=False,
            )
        )
        messages.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x55, 0x55, 0x55, 0x55, 0x55, 0x55],
                is_extended_id=False,
            )
        )

        task = self._send_bus.send_periodic(messages, self.PERIOD)
        self.assertIsInstance(task, can.broadcastmanager.CyclicSendTaskABC)

        # Take advantage of kernel's queueing mechanisms
        time.sleep(len(messages) * 2)
        task.stop()

        for tx_message in messages:
            rx_message = self._recv_bus.recv(self.TIMEOUT)

            self.assertIsNotNone(rx_message)
            self.assertEqual(tx_message.arbitration_id, rx_message.arbitration_id)
            self.assertEqual(tx_message.dlc, rx_message.dlc)
            self.assertEqual(tx_message.data, rx_message.data)
            self.assertEqual(tx_message.is_extended_id, rx_message.is_extended_id)
            self.assertEqual(tx_message.is_remote_frame, rx_message.is_remote_frame)
            self.assertEqual(tx_message.is_error_frame, rx_message.is_error_frame)
            self.assertEqual(tx_message.is_fd, rx_message.is_fd)

    def test_modifiable(self):
        messages_odd = []
        messages_odd.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x11, 0x11, 0x11, 0x11, 0x11, 0x11],
                is_extended_id=False,
            )
        )
        messages_odd.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x33, 0x33, 0x33, 0x33, 0x33, 0x33],
                is_extended_id=False,
            )
        )
        messages_odd.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x55, 0x55, 0x55, 0x55, 0x55, 0x55],
                is_extended_id=False,
            )
        )
        messages_even = []
        messages_even.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x22, 0x22, 0x22, 0x22, 0x22, 0x22],
                is_extended_id=False,
            )
        )
        messages_even.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x44, 0x44, 0x44, 0x44, 0x44, 0x44],
                is_extended_id=False,
            )
        )
        messages_even.append(
            can.Message(
                arbitration_id=0x401,
                data=[0x66, 0x66, 0x66, 0x66, 0x66, 0x66],
                is_extended_id=False,
            )
        )

        task = self._send_bus.send_periodic(messages_odd, self.PERIOD)
        self.assertIsInstance(task, can.broadcastmanager.CyclicSendTaskABC)

        # Take advantage of kernel's queueing mechanisms
        time.sleep(len(messages_odd) * 2)
        task.modify_data(messages_even)
        time.sleep(len(messages_even) * 2)

        results = []
        while True:
            result = self._recv_bus.recv(self.TIMEOUT)
            if result:
                results.append(result)
            else:
                break

        task.stop()

        # Partition results into even and odd data
        results_even = list(filter(lambda message: message.data[0] % 2 == 0, results))
        results_odd = list(filter(lambda message: message.data[0] % 2 == 1, results))

        # Make sure we received some messages
        self.assertTrue(len(results_even) != 0)
        self.assertTrue(len(results_odd) != 0)

        # Find starting index for each
        start_index_even = self._find_start_index(messages_even, results_even[0])
        self.assertTrue(start_index_even != -1)

        start_index_odd = self._find_start_index(messages_odd, results_odd[0])
        self.assertTrue(start_index_odd != -1)

        # Now go through the partitioned results and assert that they're equal
        for rx_message in results_even:
            tx_message = messages_even[start_index_even]

            self.assertEqual(tx_message.arbitration_id, rx_message.arbitration_id)
            self.assertEqual(tx_message.dlc, rx_message.dlc)
            self.assertEqual(tx_message.data, rx_message.data)
            self.assertEqual(tx_message.is_extended_id, rx_message.is_extended_id)
            self.assertEqual(tx_message.is_remote_frame, rx_message.is_remote_frame)
            self.assertEqual(tx_message.is_error_frame, rx_message.is_error_frame)
            self.assertEqual(tx_message.is_fd, rx_message.is_fd)

            start_index_even = (start_index_even + 1) % len(messages_even)

        for rx_message in results_odd:
            tx_message = messages_odd[start_index_odd]

            self.assertEqual(tx_message.arbitration_id, rx_message.arbitration_id)
            self.assertEqual(tx_message.dlc, rx_message.dlc)
            self.assertEqual(tx_message.data, rx_message.data)
            self.assertEqual(tx_message.is_extended_id, rx_message.is_extended_id)
            self.assertEqual(tx_message.is_remote_frame, rx_message.is_remote_frame)
            self.assertEqual(tx_message.is_error_frame, rx_message.is_error_frame)
            self.assertEqual(tx_message.is_fd, rx_message.is_fd)

            start_index_odd = (start_index_odd + 1) % len(messages_odd)


if __name__ == "__main__":
    unittest.main()
