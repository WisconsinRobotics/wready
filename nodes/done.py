#!/usr/bin/env python3

import sys

import rospy
from std_msgs.msg import Empty

def main():
    rospy.init_node('wready_done', anonymous=True)
    
    wready_ns = '/wready' if len(sys.argv) < 2 else sys.argv[1]
    pub_done = rospy.Publisher(f'{wready_ns}/done', Empty, queue_size=0)
    pub_done.publish(Empty())

if __name__ == '__main__':
    main()
