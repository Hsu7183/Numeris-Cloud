"""測試程序在coverage開始前載入NumPy。

Windows應用程式控制搭配Python 3.13的trace hook會阻止NumPy原生模組於
追蹤啟動後首次載入；預先載入不影響正式應用程式。
"""

import numpy  # noqa: F401
