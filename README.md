# WReady

This is a ROS package that allows for sequential initialization of other nodes.
The idea is that some sets of nodes cannot simultaneously perform certain initialization steps; for instance, two HID nodes might simultaneously ask for the user to press a button on the input device, resulting in a conflict.
To deal with this, WReady provides an interface for other nodes to register initialization steps, which it then schedules sequentially to avoid conflicts.
This software is designed for ROS Noetic and Python 3.8.x.

## Protocol

All inter-node communication is handled via services, as we want to avoid any persistent connections associated with publishers and subscribers.

1. Client sends `wready/InitRequest` with client's notify topic to `(wready)/request`, WReady responds with newly-assigned init slot ID
2. WReady schedules init slot for client
3. WReady sends `wready/InitNotify` with init slot ID to client's notify service
4. Client completes initialization work, optionally sending `wready/InitProgress` to `(wready)/progress`
5. Client sends `std_srvs/Empty` to `(wready)/done`

## Reference Implementation

A reference implementation of a WReady server and WReady client are included in this package.
These are given in the `wready.wready_client` and `wready.wready_server` modules.
For more information, see the doc comments in the respective module files.

Additionally, a full WReady server implementation exists in `nodes/default_server.py`, which is launched by `default_server.launch`.
This implementation simply prints information about WReady tasks to rosout.
For more information, see the doc comments in that file.

## Other Notes

The `nodes/done.py` node sends a `std_srvs/Empty` request to a topic as specified in its args.
This is useful for manually completing a task that the original client failed to complete for whatever reason.
