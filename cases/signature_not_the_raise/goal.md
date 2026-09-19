In `box.py`, `area` takes a width and a height and neither has a default: a caller that leaves one out is a TypeError raised by the call itself, not by anything the function does.
