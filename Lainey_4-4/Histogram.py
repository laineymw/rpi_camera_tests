import cv2, copy, os
import numpy as np
import matplotlib.pyplot as plt
from skimage.filters.rank import entropy
from skimage.morphology import disk

def showImageAndHistogram(array, histo, title="test", numBins=256):
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))

    # Left side → histogram
    axes[0].hist(histo.ravel(), bins=numBins, color='gray')
    axes[0].set_title('Histogram')
    axes[0].set_xlabel('Pixel Intensity')
    axes[0].set_ylabel('Frequency')

    # Right side → image
    axes[1].imshow(array, cmap='gray')
    axes[1].set_title(title)
    axes[1].axis('off')

    plt.tight_layout()
    plt.show()

def threshold_mean_std(im: np.ndarray, k=3):
    return im.mean() + (k * im.std())

image_folder = r"/home/r/Desktop"

for filename in os.listdir(image_folder):
    if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".bmp")):
        continue

    filepath = os.path.join(image_folder, filename)
    print(f"Processing {filename}...")

    # Load and preprocess
    original_array = cv2.imread(filepath, -1)[:,:,1]   # extract green channel
    original_array = cv2.resize(original_array, (1000, 1000))

    # Gaussian smoothing
    gaussian_array = cv2.GaussianBlur(original_array, (7, 7), 5)

    # Entropy filter
    entropy_array = entropy(gaussian_array, disk(10))
    uint8_array = (entropy_array * (255 / entropy_array.max())).astype(np.uint8)

    # Threshold
    threshold_array = copy.deepcopy(uint8_array)
    threshold = threshold_mean_std(threshold_array)
    threshold_array[threshold_array < threshold] = 0

    # Show results (image right, histogram left)
    nonzero_values = threshold_array[threshold_array > 0]
    showImageAndHistogram(threshold_array, nonzero_values, f"{filename} — After Thresholding")


# Show results (image right, histogram left)
nonzero_values = threshold_array[threshold_array > 0]
showImageAndHistogram(threshold_array, nonzero_values, "After Thresholding")