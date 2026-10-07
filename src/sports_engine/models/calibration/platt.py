from sklearn.calibration import CalibratedClassifierCV


def platt_calibrator(prefit_estimator: object) -> CalibratedClassifierCV:
    return CalibratedClassifierCV(prefit_estimator, method="sigmoid", cv="prefit")
