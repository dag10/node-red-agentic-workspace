# Task
Create a helper script that, for a specified json file and nodeid, returns its estimated size. Try to be as accurate as possible, and feel free to use web searches and look at screenshots of nodered flows if useful. Remember:
- The text on a node is not monospace, so capital H is much wider than e.g. lowercase l.
- The height of all nodes depends on how many outputs it has. 1 and 2 are the standard height, and it starts to get taller with 3+ outputs.
Also let the script work for group ids. Size is basically going to be the bounds of its combined inner nodes, accounting for their sizes, plus some padding in the group.
