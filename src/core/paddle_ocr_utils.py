import cv2
import numpy as np
from src.core.db_postprocess import DBPostProcess


def resize_heatmap_to_original(
    heatmap: np.ndarray, original_size: tuple[int, int], model_w: int, model_h: int
) -> np.ndarray:
    """
    Resize model output heatmap to match original image size, undoing aspect ratio padding.

    Args:
        heatmap (np.ndarray): Model output heatmap of shape (model_h, model_w) or (model_h, model_w, C).
        original_size (tuple): Original image size as (height, width).
        model_w (int): Model input width.
        model_h (int): Model input height.

    Returns:
        np.ndarray: Heatmap resized to original image size.
    """
    orig_h, orig_w = original_size
    scale = min(model_w / orig_w, model_h / orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    x_offset = (model_w - new_w) // 2
    y_offset = (model_h - new_h) // 2

    # Crop the heatmap to remove padding
    cropped_heatmap = heatmap[y_offset : y_offset + new_h, x_offset : x_offset + new_w]

    # Resize back to original image size
    resized_heatmap = cv2.resize(
        cropped_heatmap, (orig_w, orig_h), interpolation=cv2.INTER_CUBIC
    )

    return resized_heatmap


def get_cropped_text_images(
    heatmap, orig_img, model_height, model_width, bin_thresh=0.3
):
    """
    Extracts cropped and rectified text regions from a detection heatmap by applying postprocessing
    (e.g., differentiable binarization and contour extraction), then cropping and masking the regions
    from the original image.

    Args:
        heatmap (np.ndarray): Raw heatmap output from the detection model (shape: [1, H, W]).
        orig_img (np.ndarray): Original input image.
        model_height (int): Height of the input to the detection model.
        model_width (int): Width of the input to the detection model.
        bin_thresh (float, optional): Threshold used to binarize the heatmap for contour extraction.
                                      Defaults to 0.3.

    Returns:
        Tuple[List[np.ndarray], List[List[int]]]:
            - List of rectified cropped image regions corresponding to detected text areas.
            - List of bounding boxes in the format [x, y, w, h] for each detected text region
              in the original image coordinate space.
    """
    postprocess = DBPostProcess(
        thresh=bin_thresh,  # binary threshold
        box_thresh=0.6,
        max_candidates=1000,
        unclip_ratio=1.5,
    )

    heatmap_resized = resize_heatmap_to_original(
        heatmap,
        original_size=orig_img.shape[:2],
        model_w=model_width,
        model_h=model_height,
    )

    # mimic batch output shape
    preds = {"maps": heatmap_resized[None, None, :, :]}  # shape: [1, 1, H, W]

    # Apply postprocess to get boxes
    boxes_batch = postprocess(preds, [(*orig_img.shape[:2], 1.0, 1.0)])
    boxes = boxes_batch[0]["points"]
    cropped_images = []
    boxes_location = []
    for box in boxes:
        try:
            box = np.array(box).astype(np.int32)
            # Bounding rect
            x, y, w, h = cv2.boundingRect(box)
            boxes_location.append([x, y, w, h])
            # Crop + mask
            cropped = orig_img[y : y + h, x : x + w].copy()
            box[:, 0] -= x
            box[:, 1] -= y

            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [box], 255)  # type: ignore
            cropped = cv2.bitwise_and(cropped, cropped, mask=mask)

            # Optionally: rectify to rectangle
            rectified = warp_to_rectangle(cropped, box)

            cropped_images.append(rectified)
        except Exception as e:
            print(f"Error processing box: {box} | {e}")

    return cropped_images, boxes_location


def warp_to_rectangle(image, poly):
    """
    Warps an arbitrary quadrilateral region into a rectangle for recognition.

    Args:
        image: Input image.
        poly: 4-point polygon

    Returns:
        Warped (rectified) image.
    """
    poly = poly.astype(np.float32)
    w = int(np.linalg.norm(poly[0] - poly[1]))
    h = int(np.linalg.norm(poly[0] - poly[3]))
    dst_pts = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(poly, dst_pts)
    warped = cv2.warpPerspective(image, M, (w, h), flags=cv2.INTER_LINEAR)
    return warped


def det_postprocess(infer_results, orig_img, model_height, model_width):
    """
    Applies postprocessing to the detection model output to extract text region bounding boxes
    and their corresponding cropped image regions.

    Args:
        infer_results (np.ndarray): Raw output from the detection model, expected shape (1, H, W, C).
        orig_img (np.ndarray): The original input image.
        model_height (int): Height of the model input.
        model_width (int): Width of the model input.

    Returns:
        Tuple:
            - List of cropped image regions corresponding to detected text areas.
            - List of bounding boxes for the detected regions in the original image coordinates.
    """
    heatmap = infer_results[:, :, 0]
    return get_cropped_text_images(heatmap, orig_img, model_height, model_width)
