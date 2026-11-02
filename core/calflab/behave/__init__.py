"""Behaviors from reference footage (ADR-073).

Footage -> keypoint tracks (made outside CALFLAB with a pose tracker such as
DeepLabCut or SLEAP, or by hand) -> joint angles of the robot (a retarget
map) -> a motion clip in the project's motion library -> played, with
variation, by the stochastic ``behaviors`` controller. Each clip is checked
against the body (ranges, servo speed) before it is used.
"""

from calflab.behave.keypoints import KeypointTracks, read_tracks
from calflab.behave.retarget import RetargetMap, load_map, retarget

__all__ = ["KeypointTracks", "RetargetMap", "load_map", "read_tracks", "retarget"]
