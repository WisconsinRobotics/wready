#!/usr/bin/env python3

import sys

import rospy
from std_srvs.srv import Empty

def main():
    rospy.init_node('wready_done', anonymous=True)
    
    wready_ns = '/wready' if len(sys.argv) < 2 else sys.argv[1]
    cli_done = rospy.ServiceProxy(f'{wready_ns}/done', Empty)
    cli_done()

if __name__ == '__main__':
    main()
