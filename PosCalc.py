from math import ceil
import matplotlib.pyplot as plt
import numpy as np

def calculateCoOrds (xOrigin, yOrigin, row, col, nRows, nCols, RowHeight, ColumnWidth):
    Coordinates = []
    if nRows % 2 == 0:
        y = yOrigin - (RowHeight * (abs(row)-0.5)*(row/abs(row)))
    else:
        y = yOrigin + (row * RowHeight)
   
    if nCols % 2 == 0:
        x = xOrigin - (ColumnWidth * (abs(col)-0.5)*(col/abs(col)))
    else:
        x = xOrigin + (col * ColumnWidth)
    Coordinates.append(x)
    Coordinates.append(y)

    return Coordinates

def getRowsOrCols (Amount):
    RowsOrCols = []
    if Amount % 2 == 0:
        for i in range(-Amount // 2, 0):
            RowsOrCols.append(i)
        for i in range (1, (Amount // 2) + 1):
            RowsOrCols.append(i)

    else:
        for i in range (0, Amount):
            j = i - (Amount - 1) / 2
            RowsOrCols.append(j)
    return RowsOrCols

def getCoordinates (xOrigin, yOrigin, ScanWidth_mm, ScanHeight_mm, Overlap,
                    ImageWidthPix = 1024, ImageHeightPix = 760, PixToMm = 2.55/286):

    ImageWidth_mm = PixToMm * ImageWidthPix
    ImageHeight_mm = PixToMm * ImageHeightPix
    FinalWidth = ImageWidth_mm * (1 - (2 * Overlap))
    FinalHeight = ImageHeight_mm * (1 - (2 * Overlap))

    nColumns = ceil(ScanWidth_mm / FinalWidth)
    nRows = ceil(ScanHeight_mm / FinalHeight)

    Rows = []
    Columns = []
    Rows = getRowsOrCols(nRows)
    Columns = getRowsOrCols(nColumns)

    RowHeight = ScanHeight_mm / nRows
    ColumnWidth = ScanWidth_mm / nColumns

    Coordinates = []

    for i in Rows:
        for j in Columns:
            CoordinatePair = calculateCoOrds(xOrigin, yOrigin, i, j, nRows, nColumns, RowHeight, ColumnWidth)
            Coordinates.append(CoordinatePair)

    return Coordinates

def snakeCoordinates (xOrigin, yOrigin, ScanWidth_mm, ScanHeight_mm, Overlap,
                    ImageWidthPix = 1024, ImageHeightPix = 760, PixToMm = 2.55/286):

    ImageWidth_mm = PixToMm * ImageWidthPix
    ImageHeight_mm = PixToMm * ImageHeightPix
    FinalWidth = ImageWidth_mm * (1 - (2 * Overlap))
    FinalHeight = ImageHeight_mm * (1 - (2 * Overlap))

    nColumns = ceil(ScanWidth_mm / FinalWidth)
    nRows = ceil(ScanHeight_mm / FinalHeight)

    Rows = []
    Columns = []
    Rows = getRowsOrCols(nRows)
    Columns = getRowsOrCols(nColumns)

    RowHeight = ScanHeight_mm / nRows
    ColumnWidth = ScanWidth_mm / nColumns

    Coordinates = []

    counter = 0
    for i in Rows:
        if counter % 2 == 0:
            for j in Columns:
                CoordinatePair = calculateCoOrds(xOrigin, yOrigin, i, j, nRows, nColumns, RowHeight, ColumnWidth)
                Coordinates.append(CoordinatePair)
        else:
            for j in reversed(Columns):
                CoordinatePair = calculateCoOrds(xOrigin, yOrigin, i, j, nRows, nColumns, RowHeight, ColumnWidth)
                Coordinates.append(CoordinatePair)
        counter += 1

    return Coordinates

xOrigin = -10
yOrigin = 10
ScanWidth_mm = 20
ScanHeight_mm = 20
Overlap = 0.1
sampleCoordinates = snakeCoordinates(xOrigin, yOrigin, ScanWidth_mm, ScanHeight_mm, Overlap)

# Convert list of lists into x and y lists
xs = [p[0] for p in sampleCoordinates]
ys = [p[1] for p in sampleCoordinates]

# Compute axis limits with padding
x_min, x_max = min(xs + [xOrigin]), max(xs + [xOrigin])
y_min, y_max = min(ys + [yOrigin]), max(ys + [yOrigin])

plt.plot(xOrigin,yOrigin,'b*')

# Apply padded limits
plt.xlim(x_min - 2, x_max + 2)
plt.ylim(y_min - 2, y_max + 2)

for i,val in enumerate(sampleCoordinates):
    x, y = val
    plt.plot(x, y, 'o')
    plt.text(x, y - 0.5, f'P{i}: ({x:.2f}, {y:.2f})', ha='center', va='top', fontsize = 8)

plt.show()

for i,val in enumerate(sampleCoordinates):
    print (val)
