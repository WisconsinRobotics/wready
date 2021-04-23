#!/usr/bin/env python3

import sys

import rospy
from std_srvs.srv import Empty

def main():
    """Sends a "done" notification to a WReady server.

    This is useful if, for instance, a WReady client dies and is
    unable to signal that a task was completed. In that case,
    this script could be used to manually signal task completion
    to the server.

    The server namespace is specified as a command-line argument.
    If no namespace is specified, then `/wready` is used by
    default.
    """
    rospy.init_node('wready_done', anonymous=True)
    
    wready_ns = '/wready' if len(sys.argv) < 2 else sys.argv[1]
    cli_done = rospy.ServiceProxy(f'{wready_ns}/done', Empty)
    cli_done()

if __name__ == '__main__':
    main()
