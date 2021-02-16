# WReady

This is a ROS package that allows for sequential initialization of other nodes.
The idea is that some sets of nodes cannot simultaneously perform certain initialization steps; for instance, two HID nodes might simultaneously ask for the user to press a button on the input device, resulting in a conflict.
To deal with this, WReady provides an interface for other nodes to register initialization steps, which it then schedules sequentially to avoid conflicts.
This software is designed for ROS Noetic and Python 3.8.x.

## Protocol

1. Client sends `wready/InitRequest` with client's notify topic to `(wready)/request`, WReady responds with newly-assigned init slot ID
2. WReady schedules init slot for client
3. WReady sends `std_msgs/InitNotify` with init slot ID to client's notify topic
4. Client completes initialization work, optionally sending `wready/InitProgress` to `(wready)/progress`
5. Client sends `std_msgs/Empty` to `(wready)/done`
