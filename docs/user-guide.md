# User Guide

## Installation

1. Download the latest release ZIP from GitHub Releases.
2. Open Blender 4.2 or later.
3. Go to `Edit > Preferences > Add-ons` or `Extensions`.
4. Install the ZIP package and enable **BVH Motion Retargeter**.
5. Open the 3D Viewport, press `N`, and select the `BVH Retarget` tab.
6. Use **Language / 界面语言** at the top of the panel to select Auto, 简体中文 or English.

## Editable VMD

Select **VMD**, choose a source file and import it to the reference armature or a selected compatible MMD rig. Edit the Action, then choose **Preserve Imported VMD** to export the edited motion while retaining other source records. Saving the Blender project retains the source VMD and editing session.

For new motion from another skeleton, use **New FK Motion** and match the target bone names, rest axes and units. See the [VMD workflow](vmd-workflow.md) for mapping and sampling details.

## Basic conversion

1. Select a BVH source file.
2. Keep the built-in mapping unless the BVH uses custom bone names.
3. Choose a target rig profile and binding mode.
4. Select the target armature when using a binding workflow.
5. Click the main retarget button.

Character templates include **White**, **Black** and a **Custom** file option. Retired built-in colour selections migrate to White when an existing project is opened.

## Export

- `Auto` chooses a preset from the target rig profile.
- `Mixamo FBX` creates general Mixamo-compatible output.
- `UE4 FBX` uses Unreal Engine 4 humanoid settings.
- `UE5 FBX` uses Unreal Engine 5-friendly settings.

Enable `Auto Export After Convert` to export immediately after a successful conversion.

## VRM body retargeting

Import the VRM model first, select its armature, and choose `VRM Humanoid Body`. The add-on maps only humanoid body bones and ignores secondary `J_Sec_*` bones.

Use `VRM Leg Axis Correction` and the independent knee controls only when the thigh or knee area needs local-axis correction.
