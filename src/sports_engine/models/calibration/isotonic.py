from sklearn.calibration import CalibratedClassifierCV


def isotonic_calibrator(prefit_estimator: object) -> CalibratedClassifierCV:
    return CalibratedClassifierCV(prefit_estimator, method="isotonic", cv="prefit")
