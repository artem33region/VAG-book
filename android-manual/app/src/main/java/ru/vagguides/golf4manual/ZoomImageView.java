package ru.vagguides.golf4manual;

import android.annotation.SuppressLint;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Matrix;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;
import android.util.AttributeSet;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.widget.ImageView;

public final class ZoomImageView extends ImageView implements ScaleGestureDetector.OnScaleGestureListener {
    private final Matrix drawMatrix = new Matrix();
    private final ScaleGestureDetector scaleDetector;
    private final GestureDetector gestureDetector;
    private float baseScale = 1f;
    private float currentScale = 1f;
    private float lastX;
    private float lastY;
    private boolean laidOut;

    public ZoomImageView(Context context) {
        this(context, null);
    }

    public ZoomImageView(Context context, AttributeSet attrs) {
        super(context, attrs);
        setScaleType(ScaleType.MATRIX);
        setBackgroundColor(0xFF20262D);
        scaleDetector = new ScaleGestureDetector(context, this);
        gestureDetector = new GestureDetector(context, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onDown(MotionEvent event) {
                return true;
            }

            @Override
            public boolean onSingleTapConfirmed(MotionEvent event) {
                return performClick();
            }

            @Override
            public boolean onDoubleTap(MotionEvent event) {
                float target = currentScale < baseScale * 1.8f ? baseScale * 2.6f : baseScale;
                float factor = target / currentScale;
                drawMatrix.postScale(factor, factor, event.getX(), event.getY());
                currentScale = target;
                constrainMatrix();
                setImageMatrix(drawMatrix);
                return true;
            }
        });
    }

    @Override
    public void setImageBitmap(Bitmap bitmap) {
        super.setImageBitmap(bitmap);
        post(this::resetZoom);
    }

    @Override
    protected void onSizeChanged(int width, int height, int oldWidth, int oldHeight) {
        super.onSizeChanged(width, height, oldWidth, oldHeight);
        laidOut = width > 0 && height > 0;
        if (laidOut && getDrawable() != null) {
            resetZoom();
        }
    }

    public void resetZoom() {
        Drawable drawable = getDrawable();
        if (!laidOut || drawable == null || drawable.getIntrinsicWidth() <= 0 || drawable.getIntrinsicHeight() <= 0) {
            return;
        }
        float viewWidth = getWidth() - getPaddingLeft() - getPaddingRight();
        float viewHeight = getHeight() - getPaddingTop() - getPaddingBottom();
        baseScale = Math.min(viewWidth / drawable.getIntrinsicWidth(), viewHeight / drawable.getIntrinsicHeight());
        currentScale = baseScale;
        float dx = getPaddingLeft() + (viewWidth - drawable.getIntrinsicWidth() * baseScale) / 2f;
        float dy = getPaddingTop() + (viewHeight - drawable.getIntrinsicHeight() * baseScale) / 2f;
        drawMatrix.reset();
        drawMatrix.postScale(baseScale, baseScale);
        drawMatrix.postTranslate(dx, dy);
        setImageMatrix(drawMatrix);
    }

    @Override
    @SuppressLint("ClickableViewAccessibility") // onSingleTapConfirmed calls performClick.
    public boolean onTouchEvent(MotionEvent event) {
        gestureDetector.onTouchEvent(event);
        scaleDetector.onTouchEvent(event);

        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                lastX = event.getX();
                lastY = event.getY();
                getParent().requestDisallowInterceptTouchEvent(true);
                break;
            case MotionEvent.ACTION_MOVE:
                if (!scaleDetector.isInProgress() && event.getPointerCount() == 1) {
                    float dx = event.getX() - lastX;
                    float dy = event.getY() - lastY;
                    drawMatrix.postTranslate(dx, dy);
                    constrainMatrix();
                    setImageMatrix(drawMatrix);
                }
                lastX = event.getX();
                lastY = event.getY();
                break;
            case MotionEvent.ACTION_POINTER_UP:
                // Start the next drag at the surviving finger, not the pre-pinch point.
                int remaining = event.getActionIndex() == 0 ? 1 : 0;
                lastX = event.getX(remaining);
                lastY = event.getY(remaining);
                break;
            case MotionEvent.ACTION_UP:
                getParent().requestDisallowInterceptTouchEvent(false);
                break;
            case MotionEvent.ACTION_CANCEL:
                getParent().requestDisallowInterceptTouchEvent(false);
                break;
            default:
                break;
        }
        return true;
    }

    @Override
    public boolean performClick() {
        super.performClick();
        return true;
    }

    @Override
    public boolean onScale(ScaleGestureDetector detector) {
        float target = Math.max(baseScale, Math.min(baseScale * 5f, currentScale * detector.getScaleFactor()));
        float factor = target / currentScale;
        drawMatrix.postScale(factor, factor, detector.getFocusX(), detector.getFocusY());
        currentScale = target;
        constrainMatrix();
        setImageMatrix(drawMatrix);
        return true;
    }

    @Override
    public boolean onScaleBegin(ScaleGestureDetector detector) {
        return true;
    }

    @Override
    public void onScaleEnd(ScaleGestureDetector detector) {
        constrainMatrix();
        setImageMatrix(drawMatrix);
    }

    private void constrainMatrix() {
        Drawable drawable = getDrawable();
        if (drawable == null) {
            return;
        }
        RectF bounds = new RectF(0, 0, drawable.getIntrinsicWidth(), drawable.getIntrinsicHeight());
        drawMatrix.mapRect(bounds);
        float left = getPaddingLeft();
        float top = getPaddingTop();
        float right = getWidth() - getPaddingRight();
        float bottom = getHeight() - getPaddingBottom();
        float dx = 0f;
        float dy = 0f;

        if (bounds.width() <= right - left) {
            dx = left + (right - left - bounds.width()) / 2f - bounds.left;
        } else if (bounds.left > left) {
            dx = left - bounds.left;
        } else if (bounds.right < right) {
            dx = right - bounds.right;
        }

        if (bounds.height() <= bottom - top) {
            dy = top + (bottom - top - bounds.height()) / 2f - bounds.top;
        } else if (bounds.top > top) {
            dy = top - bounds.top;
        } else if (bounds.bottom < bottom) {
            dy = bottom - bounds.bottom;
        }
        drawMatrix.postTranslate(dx, dy);
    }
}
