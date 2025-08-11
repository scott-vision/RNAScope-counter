# RNAScope-counter

User interface for spot counting and intensity calculation for RNAScope analysis.

PyQt6 interface to open 3-channel large montages, define a ROI for each section of the Brain, then uses find maxima to detect spots.

The three channels should be:
- Nuclei, 488 nm, DAPI
- GOB, 560 nm, Opal 570
- GOA, 650 nm, Opal 650


Takes in the paths to 2 montage images (hippocampus and thalamus), maximum projects them and allows the user to select ROIs, the first image displayed is of the hippocampus and allows the user to define 3 rois:
- CA1
- CA3
- DG
Second montage is of the Thalamus and user only defines one region to quantify (Thalamus).

Then provides analysis of each reigon defined, including:
- Number of spots in GOA/GOB channel
- Intensity of spots
- Average spot intensity
- Spots per square micron

Output is saved to CSV file

## Usage

```bash
python -m rnascope_counter --hippocampus path/to/hippo.tif --thalamus path/to/thalamus.tif --output results.csv [--max-projected]
```

At startup the application prompts for the pixel spacing in microns per pixel (default `0.4475`).
This value is used to compute the area of each ROI and the corresponding spot density.
Use the `--max-projected` flag if the provided images are already maximum projected.
