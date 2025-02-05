#!/usr/bin/env python3
import numpy as np
import os
import shutil
from os import path
from cereal import car
from selfdrive.config import Conversions as CV
from selfdrive.car.hyundai.values import Ecu, ECU_FINGERPRINT, CAR, FINGERPRINTS, Buttons, FEATURES
from selfdrive.car import STD_CARGO_KG, scale_rot_inertia, scale_tire_stiffness, gen_empty_fingerprint
from selfdrive.car.interfaces import CarInterfaceBase
from selfdrive.controls.lib.lateral_planner import LANE_CHANGE_SPEED_MIN
from common.params import Params
from selfdrive.car.hyundai.carstate import CarStateBase, CarState


GearShifter = car.CarState.GearShifter
EventName = car.CarEvent.EventName
ButtonType = car.CarState.ButtonEvent.Type

class CarInterface(CarInterfaceBase):
  def __init__(self, CP, CarController, CarState):
    super().__init__(CP, CarController, CarState)
    self.cp2 = self.CS.get_can2_parser(CP)
    self.mad_mode_enabled = Params().get_bool('MadModeEnabled')

  @staticmethod
  def compute_gb(accel, speed):
    return float(accel) / 3.0

  @staticmethod
  def get_params(candidate, fingerprint=gen_empty_fingerprint(), has_relay=False, car_fw=[]):  # pylint: disable=dangerous-default-value
    ret = CarInterfaceBase.get_std_params(candidate, fingerprint, has_relay)
    ret.openpilotLongitudinalControl = Params().get_bool('LongControlEnabled')

    ret.carName = "hyundai"
    ret.safetyModel = car.CarParams.SafetyModel.hyundai

    # Most Hyundai car ports are community features for now
    ret.communityFeature = True

    tire_stiffness_factor = 1.

    eps_modified = False
    for fw in car_fw:
      if fw.ecu == "eps" and b"," in fw.fwVersion:
        eps_modified = True

    ret.maxSteeringAngleDeg = 200.
    UseLQR = Params().get_bool('UseLQR')

    # lateral LQR global hyundai
    if UseLQR:
      ret.lateralTuning.init('lqr')

      ret.lateralTuning.lqr.scale = 1650.
      ret.lateralTuning.lqr.ki = 0.01
      ret.lateralTuning.lqr.dcGain = 0.00275

      ret.lateralTuning.lqr.a = [0., 1., -0.22619643, 1.21822268]
      ret.lateralTuning.lqr.b = [-1.92006585e-04, 3.95603032e-05]
      ret.lateralTuning.lqr.c = [1., 0.]
      ret.lateralTuning.lqr.k = [-110., 451.]
      ret.lateralTuning.lqr.l = [0.33, 0.318]


    ret.steerActuatorDelay = 0.0
    ret.steerLimitTimer = 2.5
    ret.steerRateCost = 0.4
    ret.steerMaxBP = [0.]
    ret.steerMaxV = [1.5]

   #Longitudinal Tune and logic for car tune
    if candidate is not CAR.GENESIS_G70 or CAR.STINGER or CAR.GENESIS or CAR.GENESIS_G80 or CAR.KONA or CAR.KONA_EV or CAR.GENESIS_EQ900 or CAR.GENESIS_G90: #Tune for untuned cars
      # Donfyffe stock tune for untuned cars
      
      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.1]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]

      ret.longitudinalTuning.kpBP = [0, 10.*CV.KPH_TO_MS, 20.*CV.KPH_TO_MS, 40.*CV.KPH_TO_MS, 70.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [1.23, 0.97, 0.83, 0.68, 0.57, 0.48, 0.38]
      ret.longitudinalTuning.kiBP = [0, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kiV = [0.03, 0.02]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.6, 0.65, 0.55, 0.45, 0.35, 0.25]

    ret.gasMaxBP = [0., 10.*CV.KPH_TO_MS, 20.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 70.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
    ret.brakeMaxBP = [0, 70.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
    ret.brakeMaxV = [2.3, 1.5, 0.8]
    ret.longitudinalTuning.deadzoneBP = [0., 100. * CV.KPH_TO_MS]
    ret.longitudinalTuning.deadzoneV = [0., 0.015]

    ret.stoppingBrakeRate = 0.12  # brake_travel/s while trying to stop
    ret.startingBrakeRate = 1.0  # brake_travel/s while releasing on restart
    ret.startAccel = 1.5

    # genesis
    if candidate == CAR.GENESIS:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Genesis.png img_spinner_comma.png")
      ret.mass = 1900. + STD_CARGO_KG
      ret.wheelbase = 3.01
      ret.centerToFront = ret.wheelbase * 0.4
      ret.minSteerSpeed = 60 * CV.KPH_TO_MS
      ret.steerRatio = 16.5

    elif candidate == CAR.GENESIS_G70:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Genesis.png img_spinner_comma.png")
      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.65]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]

      ret.steerRatio = 13.56
      ret.mass = 1640. + STD_CARGO_KG
      ret.wheelbase = 2.84
      ret.centerToFront = ret.wheelbase * 0.4
      ret.longitudinalTuning.kpBP = [0, 10. * CV.KPH_TO_MS, 20. * CV.KPH_TO_MS, 40. * CV.KPH_TO_MS, 70. * CV.KPH_TO_MS, 100. * CV.KPH_TO_MS, 130. * CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [0.6, 0.58, 0.55, 0.48, 0.45, 0.40, 0.35]
      ret.longitudinalTuning.kiBP = [0.]
      ret.longitudinalTuning.kiV = [0.015]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.85, 0.7, 0.45, 0.3, 0.2, 0.15]

    elif candidate == CAR.GENESIS_G80:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Genesis.png img_spinner_comma.png")
      ret.mass = 1855. + STD_CARGO_KG
      ret.wheelbase = 3.01
      ret.centerToFront = ret.wheelbase * 0.4
      ret.steerRatio = 16.5
      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.1]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]

      ret.longitudinalTuning.kpBP = [0, 10.*CV.KPH_TO_MS, 20.*CV.KPH_TO_MS, 40.*CV.KPH_TO_MS, 70.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [1.2, 0.95, 0.8, 0.65, 0.53, 0.43, 0.325]
      ret.longitudinalTuning.kiBP = [0, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kiV = [0.07, 0.03]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.65, 0.65, 0.65, 0.55, 0.45, 0.35]
      
    elif candidate == CAR.GENESIS_EQ900:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Genesis.png img_spinner_comma.png")
      ret.mass = 2060. + STD_CARGO_KG
      ret.wheelbase = 3.01
      ret.steerRatio = 16.5
      ret.centerToFront = ret.wheelbase * 0.4
      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.1]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]

      ret.longitudinalTuning.kpBP = [0, 10.*CV.KPH_TO_MS, 20.*CV.KPH_TO_MS, 40.*CV.KPH_TO_MS, 70.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [1.23, 0.97, 0.83, 0.68, 0.57, 0.48, 0.38]
      ret.longitudinalTuning.kiBP = [0, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kiV = [0.07, 0.03]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.65, 0.65, 0.65, 0.55, 0.45, 0.35]

    elif candidate == CAR.GENESIS_EQ900_L:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Genesis.png img_spinner_comma.png")
      ret.mass = 2290
      ret.wheelbase = 3.45
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.GENESIS_G90:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Genesis.png img_spinner_comma.png")
      ret.mass = 2060. + STD_CARGO_KG
      ret.wheelbase = 3.01
      ret.steerRatio = 16.5
      ret.centerToFront = ret.wheelbase * 0.4

      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.1]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]

      ret.longitudinalTuning.kpBP = [0, 10.*CV.KPH_TO_MS, 20.*CV.KPH_TO_MS, 40.*CV.KPH_TO_MS, 70.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [1.23, 0.97, 0.83, 0.68, 0.57, 0.48, 0.38]
      ret.longitudinalTuning.kiBP = [0, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kiV = [0.07, 0.03]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.65, 0.65, 0.65, 0.55, 0.45, 0.35]

    # hyundai
    elif candidate in [CAR.SANTA_FE]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1694 + STD_CARGO_KG
      ret.wheelbase = 2.766
      ret.steerRatio = 13.27 * 1.15   # 15% higher at the center seems reasonable
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate in [CAR.SONATA, CAR.SONATA_HEV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1513. + STD_CARGO_KG
      ret.wheelbase = 2.84
      ret.steerRatio = 13.27 * 1.15   # 15% higher at the center seems reasonable
      ret.centerToFront = ret.wheelbase * 0.4
      tire_stiffness_factor = 0.65
    elif candidate in [CAR.SONATA19, CAR.SONATA19_HEV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 4497. * CV.LB_TO_KG
      ret.wheelbase = 2.804
      ret.steerRatio = 13.27 * 1.15   # 15% higher at the center seems reasonable
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.SONATA_LF_TURBO:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1590. + STD_CARGO_KG
      ret.wheelbase = 2.805
      tire_stiffness_factor = 0.65
      ret.steerRatio = 13.27 * 1.15   # 15% higher at the center seems reasonable
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.PALISADE:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1999. + STD_CARGO_KG
      ret.wheelbase = 2.90
      ret.centerToFront = ret.wheelbase * 0.4
      ret.steerRatio = 13.75 * 1.15
      if eps_modified:
        ret.maxSteeringAngleDeg = 1000.
    elif candidate in [CAR.ELANTRA, CAR.ELANTRA_GT_I30]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1275. + STD_CARGO_KG
      ret.wheelbase = 2.7
      tire_stiffness_factor = 0.7
      ret.steerRatio = 15.4            # 14 is Stock | Settled Params Learner values are steerRatio: 15.401566348670535
      ret.centerToFront = ret.wheelbase * 0.4
      ret.minSteerSpeed = 32 * CV.MPH_TO_MS
    elif candidate == CAR.ELANTRA_2021:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = (2800. * CV.LB_TO_KG) + STD_CARGO_KG
      ret.wheelbase = 2.72
      ret.steerRatio = 13.27 * 1.15   # 15% higher at the center seems reasonable
      tire_stiffness_factor = 0.65
    elif candidate == CAR.ELANTRA_HEV_2021:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = (3017. * CV.LB_TO_KG) + STD_CARGO_KG
      ret.wheelbase = 2.72
      ret.steerRatio = 13.27 * 1.15  # 15% higher at the center seems reasonable
      tire_stiffness_factor = 0.65
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.KONA:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1275. + STD_CARGO_KG
      ret.wheelbase = 2.7
      ret.steerRatio = 13.73 * 1.15  # Spec
      ret.centerToFront = ret.wheelbase * 0.4
      tire_stiffness_factor = 0.385
      
      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.1]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]

       #Tune To base Kona tune off of.
      ret.longitudinalTuning.kpBP = [0, 10. * CV.KPH_TO_MS, 20. * CV.KPH_TO_MS, 40. * CV.KPH_TO_MS, 70. * CV.KPH_TO_MS, 100. * CV.KPH_TO_MS, 130. * CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [1.20, 1.1, 1.05, 1.0, 0.95, 0.90, 0.85]
      ret.longitudinalTuning.kiBP = [0, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kiV = [0.07, 0.03]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.65, 0.65, 0.65, 0.55, 0.45, 0.35]

    elif candidate in [CAR.KONA_HEV, CAR.KONA_EV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1685. + STD_CARGO_KG
      ret.wheelbase = 2.7
      ret.steerRatio = 13.73  # Spec
      tire_stiffness_factor = 0.385
      ret.centerToFront = ret.wheelbase * 0.4
      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.1]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]


 #Tune To base Kona EV tune off of.
      ret.longitudinalTuning.kpBP = [0, 10. * CV.KPH_TO_MS, 20. * CV.KPH_TO_MS, 40. * CV.KPH_TO_MS, 70. * CV.KPH_TO_MS, 100. * CV.KPH_TO_MS, 130. * CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [1.20, 1.1, 1.05, 1.0, 0.95, 0.90, 0.85]
      ret.longitudinalTuning.kiBP = [0, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kiV = [0.07, 0.03]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.65, 0.65, 0.65, 0.55, 0.45, 0.35]

    elif candidate in [CAR.IONIQ, CAR.IONIQ_EV_LTD, CAR.IONIQ_EV_2020, CAR.IONIQ_PHEV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1490. + STD_CARGO_KG
      ret.steerRatio = 13.73  # Spec
      ret.wheelbase = 2.7
      tire_stiffness_factor = 0.385
      ret.centerToFront = ret.wheelbase * 0.4
      if candidate not in [CAR.IONIQ_EV_2020, CAR.IONIQ_PHEV]:
        ret.minSteerSpeed = 32 * CV.MPH_TO_MS
    elif candidate in [CAR.GRANDEUR_IG, CAR.GRANDEUR_IG_HEV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      tire_stiffness_factor = 0.8
      ret.mass = 1640. + STD_CARGO_KG
      ret.wheelbase = 2.845
      ret.maxSteeringAngleDeg = 120.
      ret.centerToFront = ret.wheelbase * 0.385
    elif candidate in [CAR.GRANDEUR_IG_FL, CAR.GRANDEUR_IG_FL_HEV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      tire_stiffness_factor = 0.8
      ret.mass = 1640. + STD_CARGO_KG
      ret.wheelbase = 2.845
      ret.maxSteeringAngleDeg = 120.
      ret.centerToFront = ret.wheelbase * 0.385
    elif candidate == CAR.VELOSTER:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 3558. * CV.LB_TO_KG
      ret.wheelbase = 2.80
      tire_stiffness_factor = 0.9
      ret.steerRatio = 13.75 * 1.15
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.TUCSON_TL_SCC:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Hyundai.png img_spinner_comma.png")
      ret.mass = 1594. + STD_CARGO_KG #1730
      ret.wheelbase = 2.67
      tire_stiffness_factor = 0.7
      ret.centerToFront = ret.wheelbase * 0.4
      ret.maxSteeringAngleDeg = 120.
      ret.startAccel = 0.5
    # kia
    elif candidate == CAR.SORENTO:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 1985. + STD_CARGO_KG
      ret.wheelbase = 2.78
      ret.steerRatio = 14.4 * 1.1   # 10% higher at the center seems reasonable
      tire_stiffness_factor = 0.7
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate in [CAR.K5, CAR.K5_HEV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 3558. * CV.LB_TO_KG
      ret.wheelbase = 2.80
      tire_stiffness_factor = 0.7
      ret.steerRatio = 13.75
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.STINGER:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Stinger.png img_spinner_comma.png")
      tire_stiffness_factor = 1.125 # LiveParameters (Tunder's 2020)
      ret.mass = 1825.0 + STD_CARGO_KG
      ret.wheelbase = 2.78
      ret.steerRatio = 14.4 * 1.15   # 15% higher at the center seems reasonable
      ret.centerToFront = ret.wheelbase * 0.4
      if not UseLQR:
        ret.lateralTuning.init('indi')
        ret.lateralTuning.indi.innerLoopGainBP = [0.]
        ret.lateralTuning.indi.innerLoopGainV = [3.65]
        ret.lateralTuning.indi.outerLoopGainBP = [0.]
        ret.lateralTuning.indi.outerLoopGainV = [2.5]
        ret.lateralTuning.indi.timeConstantBP = [0.]
        ret.lateralTuning.indi.timeConstantV = [1.4]
        ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
        ret.lateralTuning.indi.actuatorEffectivenessV = [2.]
      
      ret.longitudinalTuning.kpBP = [0, 10. * CV.KPH_TO_MS, 20. * CV.KPH_TO_MS, 40. * CV.KPH_TO_MS, 70. * CV.KPH_TO_MS, 100. * CV.KPH_TO_MS, 130. * CV.KPH_TO_MS]
      ret.longitudinalTuning.kpV = [1.185, 1.095, 1.0, 0.95, 0.90, 0.85, 0.80]
      ret.longitudinalTuning.kiBP = [0, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kiV = [0.03, 0.02]
      ret.longitudinalTuning.kfBP = [10.*CV.KPH_TO_MS, 30.*CV.KPH_TO_MS, 50.*CV.KPH_TO_MS, 80.*CV.KPH_TO_MS, 100.*CV.KPH_TO_MS, 130.*CV.KPH_TO_MS]
      ret.longitudinalTuning.kfV = [1.0, 0.92, 0.86, 0.79, 0.76, 0.72]
      ret.gasMaxV = [0.65, 0.65, 0.60, 0.55, 0.45, 0.35]

    elif candidate == CAR.FORTE:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 3558. * CV.LB_TO_KG
      ret.wheelbase = 2.80
      ret.steerRatio = 13.75
      tire_stiffness_factor = 0.7
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.CEED:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 1350. + STD_CARGO_KG
      ret.wheelbase = 2.65
      ret.steerRatio = 13.75
      tire_stiffness_factor = 0.6
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.SPORTAGE:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 1985. + STD_CARGO_KG
      ret.wheelbase = 2.78
      tire_stiffness_factor = 0.7
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate in [CAR.NIRO_HEV, CAR.NIRO_EV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 1737. + STD_CARGO_KG
      ret.wheelbase = 2.7
      ret.steerRatio = 13.73  # Spec
      tire_stiffness_factor = 0.385
      ret.centerToFront = ret.wheelbase * 0.4
      if candidate == CAR.NIRO_HEV and not Params().get_bool('UseSMDPSHarness'):
        ret.minSteerSpeed = 32 * CV.MPH_TO_MS
    elif candidate in [CAR.K7, CAR.K7_HEV]:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      tire_stiffness_factor = 0.7
      ret.mass = 1650. + STD_CARGO_KG
      ret.wheelbase = 2.855
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.SELTOS:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 1310. + STD_CARGO_KG
      ret.wheelbase = 2.6
      tire_stiffness_factor = 0.7
      ret.centerToFront = ret.wheelbase * 0.4
    elif candidate == CAR.K9:
      os.system("cd /data/openpilot/selfdrive/assets && rm -rf img_spinner_comma.png && cp Kia.png img_spinner_comma.png")
      ret.mass = 2005. + STD_CARGO_KG
      ret.wheelbase = 3.15
      ret.centerToFront = ret.wheelbase * 0.4
      tire_stiffness_factor = 0.8

    ret.radarTimeStep = 0.05

    # TODO: get actual value, for now starting with reasonable value for
    # civic and scaling by mass and wheelbase
    ret.rotationalInertia = scale_rot_inertia(ret.mass, ret.wheelbase)

    # TODO: start from empirically derived lateral slip stiffness for the civic and scale by
    # mass and CG position, so all cars will have approximately similar dyn behaviors
    ret.tireStiffnessFront, ret.tireStiffnessRear = scale_tire_stiffness(ret.mass, ret.wheelbase, ret.centerToFront,
                                                                         tire_stiffness_factor=tire_stiffness_factor)

    # no rear steering, at least on the listed cars above
    ret.steerRatioRear = 0.
    ret.steerControlType = car.CarParams.SteerControlType.torque

    ret.stoppingControl = True

    ret.enableBsm = 0x58b in fingerprint[0]
    ret.enableAutoHold = 1151 in fingerprint[0]

    # ignore CAN2 address if L-CAN on the same BUS
    ret.mdpsBus = 1 if 593 in fingerprint[1] and 1296 not in fingerprint[1] else 0
    ret.sasBus = 1 if 688 in fingerprint[1] and 1296 not in fingerprint[1] else 0
    ret.sccBus = 0 if 1056 in fingerprint[0] else 1 if 1056 in fingerprint[1] and 1296 not in fingerprint[1] \
                                                                     else 2 if 1056 in fingerprint[2] else -1

    if ret.sccBus >= 0:
      ret.hasScc13 = 1290 in fingerprint[ret.sccBus]
      ret.hasScc14 = 905 in fingerprint[ret.sccBus]

    ret.hasEms = 608 in fingerprint[0] and 809 in fingerprint[0]

    print('fingerprint', fingerprint)

    ret.radarOffCan = ret.sccBus == -1
    ret.pcmCruise = not ret.radarOffCan


    # set safety_hyundai_community only for non-SCC, MDPS harrness or SCC harrness cars or cars that have unknown issue
    if ret.radarOffCan or ret.mdpsBus == 1 or ret.openpilotLongitudinalControl or ret.sccBus == 1 or Params().get_bool('MadModeEnabled'):
      ret.safetyModel = car.CarParams.SafetyModel.hyundaiCommunity
    return ret
    

  def update(self, c, can_strings):
    self.cp.update_strings(can_strings)
    self.cp2.update_strings(can_strings)
    self.cp_cam.update_strings(can_strings)

    ret = self.CS.update(self.cp, self.cp2, self.cp_cam)
    ret.canValid = self.cp.can_valid and self.cp2.can_valid and self.cp_cam.can_valid

    if self.CP.pcmCruise and not self.CC.scc_live:
      self.CP.pcmCruise = False
    elif self.CC.scc_live and not self.CP.pcmCruise:
      self.CP.pcmCruise = True

    # most HKG cars has no long control, it is safer and easier to engage by main on

    if self.mad_mode_enabled:
      ret.cruiseState.enabled = ret.cruiseState.available

    # turning indicator alert logic
    if (ret.leftBlinker or ret.rightBlinker or self.CC.turning_signal_timer) and ret.vEgo < LANE_CHANGE_SPEED_MIN - 1.2:
      self.CC.turning_indicator_alert = True
    else:
      self.CC.turning_indicator_alert = False
      

    buttonEvents = []
    if self.CS.cruise_buttons != self.CS.prev_cruise_buttons:
      be = car.CarState.ButtonEvent.new_message()
      be.pressed = self.CS.cruise_buttons != 0
      but = self.CS.cruise_buttons if be.pressed else self.CS.prev_cruise_buttons
      if but == Buttons.RES_ACCEL:
        be.type = ButtonType.accelCruise
      elif but == Buttons.SET_DECEL:
        be.type = ButtonType.decelCruise
      elif but == Buttons.GAP_DIST:
        be.type = ButtonType.gapAdjustCruise
      #elif but == Buttons.CANCEL:
      #  be.type = ButtonType.cancel
      else:
        be.type = ButtonType.unknown
      buttonEvents.append(be)
    if self.CS.cruise_main_button != self.CS.prev_cruise_main_button:
      be = car.CarState.ButtonEvent.new_message()
      be.type = ButtonType.altButton3
      be.pressed = bool(self.CS.cruise_main_button)
      buttonEvents.append(be)
    ret.buttonEvents = buttonEvents

    events = self.create_common_events(ret)

    # low speed steer alert hysteresis logic (only for cars with steer cut off above 10 m/s)
    UseSMDPS = Params().get_bool('UseSMDPSHarness')
    
    if UseSMDPS == False and Params().get_bool('LowSpeedAlerts'):
      if ret.vEgo < (self.CP.minSteerSpeed + 2.) and self.CP.minSteerSpeed > 10.:
        self.low_speed_alert = True
      if ret.vEgo > (self.CP.minSteerSpeed + 4.):
        self.low_speed_alert = False
      if self.low_speed_alert:
        events.add(car.CarEvent.EventName.belowSteerSpeed)

    #TPMS Alerts - JPR
    if CAR.STINGER:
      minTP = 33 # Min TPMS Pressure
    elif CAR.KONA_EV or CAR.KONA_HEV or CAR.KONA:
      minTP = 30
    elif CAR.ELANTRA_HEV_2021:
      minTP = 30
    elif CAR.K5:
      minTP = 30
    elif CAR.FORTE:
      minTP = 30
    elif CAR.GENESIS:
      minTP = 30
    elif CAR.NIRO_EV:
      minTP = 30
    elif CAR.SANTA_FE:
      minTP = 30
    elif CAR.GENESIS_G80:
      minTP = 28
    else:
      minTP = 28


    if ret.tpmsFl < minTP and Params().get_bool('TPMS_Alerts'):
      events.add(car.CarEvent.EventName.fl)
    elif ret.tpmsFr < minTP and Params().get_bool('TPMS_Alerts'):
      events.add(car.CarEvent.EventName.fr)
    elif ret.tpmsRl < minTP and Params().get_bool('TPMS_Alerts'):
      events.add(car.CarEvent.EventName.rl)
    elif ret.tpmsRr < minTP and Params().get_bool('TPMS_Alerts'):
      events.add(car.CarEvent.EventName.rr)


    if self.CC.longcontrol and self.CS.cruise_unavail:
      events.add(EventName.brakeUnavailable)
    #if abs(ret.steeringAngleDeg) > self.CP.maxSteeringAngleDeg and EventName.steerSaturated not in events.events:
    #  events.add(EventName.steerSaturated)
    if self.low_speed_alert and not self.CS.mdps_bus:
      events.add(EventName.belowSteerSpeed)
    if self.CC.turning_indicator_alert:
      events.add(EventName.turningIndicatorOn)
    #if self.CS.lkas_button_on != self.CS.prev_lkas_button:
    #  events.add(EventName.buttonCancel)
    if self.mad_mode_enabled and EventName.pedalPressed in events.events:
      events.events.remove(EventName.pedalPressed)

  # handle button presses
    for b in ret.buttonEvents:
      # do disable on button down
      if b.type == ButtonType.cancel and b.pressed:
        events.add(EventName.buttonCancel)
      if self.CC.longcontrol and not self.CC.scc_live:
        # do enable on both accel and decel buttons
        if b.type in [ButtonType.accelCruise, ButtonType.decelCruise] and not b.pressed:
          events.add(EventName.buttonEnable)
        if EventName.wrongCarMode in events.events:
          events.events.remove(EventName.wrongCarMode)
        if EventName.pcmDisable in events.events:
          events.events.remove(EventName.pcmDisable)
      elif not self.CC.longcontrol and ret.cruiseState.enabled:
        # do enable on decel button only
        if b.type == ButtonType.decelCruise and not b.pressed:
          events.add(EventName.buttonEnable)

    # scc smoother
    if self.CC.scc_smoother is not None:
      self.CC.scc_smoother.inject_events(events)

    ret.events = events.to_msg()

    self.CS.out = ret.as_reader()
    return self.CS.out

  # scc smoother - hyundai only
  def apply(self, c, controls):
    can_sends = self.CC.update(c.enabled, self.CS, self.frame, c, c.actuators,
                               c.cruiseControl.cancel, c.hudControl.visualAlert, c.hudControl.leftLaneVisible,
                               c.hudControl.rightLaneVisible, c.hudControl.leftLaneDepart, c.hudControl.rightLaneDepart,
                               c.hudControl.setSpeed, c.hudControl.leadVisible, controls)
    self.frame += 1
    return can_sends
