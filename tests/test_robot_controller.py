# tests/test_robot_controller.py
import pytest
from unittest.mock import MagicMock
import configparser
import os
import math

# Assurez-vous que le chemin est correct pour votre structure
from controller_interface.GalilDriver import RobotController, GalilDriver, AXES_ORDER


# Fixture pytest pour charger la configuration une seule fois pour tous les tests
@pytest.fixture(scope="module")
def test_config():
    config = configparser.ConfigParser()
    config['RATIOS'] = {'x': '500', 'y': '-500', 'z': '400', 'theta': '200', 'phi': '-100'}
    config['OFFSETS'] = {'correction_theta_x': '50.0', 'correction_phi_l': '60.0'}
    return config


# Fixture pour créer un robot avec un driver simulé (mock)
@pytest.fixture
def robot_with_mock_driver(test_config, mocker):
    mock_driver = MagicMock(spec=GalilDriver)

    mocker.patch('os.path.exists', return_value=True)

    # On passe l'objet config directement au constructeur
    robot = RobotController(mock_driver, test_config)
    return robot, mock_driver


# --- Nos Tests Unitaires ---

def test_conversion_mm_to_steps(robot_with_mock_driver):
    robot, _ = robot_with_mock_driver
    assert robot._convert_to_steps('X', 10) == 5000
    assert robot._convert_to_steps('Y', -20) == 10000
    assert robot._convert_to_steps('Z', 5) == 2000


def test_conversion_degrees_to_steps(robot_with_mock_driver):
    robot, _ = robot_with_mock_driver
    assert robot._convert_to_steps('THETA', 90) == 18000
    assert robot._convert_to_steps('PHI', -45) == 4500


def test_move_to_single_axis(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    robot.move_to(X=10)
    mock_driver.send_cmd.assert_any_call("PA 5000,,,,,")
    mock_driver.send_cmd.assert_any_call("BG AB")
    mock_driver.wait_motion_complete.assert_called_with("AB")


def test_move_to_multiple_axes(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    robot.move_to(Y=-20, Z=5, PHI=10)

    # CORRECTION : La valeur pour Y (axe C) est à l'index 2, Z (D) à l'index 3, Phi (F) à l'index 5.
    # La chaîne correcte est donc ",,valC,valD,,valF"
    mock_driver.send_cmd.assert_any_call("PA ,,10000,2000,,-1000")
    mock_driver.send_cmd.assert_any_call("BG CDF")
    mock_driver.wait_motion_complete.assert_called_with("CDF")


# Dans tests/test_robot_controller.py

def test_go_home(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    robot.go_home()

    mock_driver.send_cmd.assert_any_call("PA 0,,0,0,0,0")
    mock_driver.send_cmd.assert_any_call("BG ABCDEF")  # L'ordre est maintenant garanti
    mock_driver.wait_motion_complete.assert_called_with("ABCDEF")


def test_jog_gantry_axis(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    robot.jog('X', 10)
    mock_driver.send_cmd.assert_any_call("JGA=5000")
    mock_driver.send_cmd.assert_any_call("JGB=-5000")


def test_update_and_get_capsule_position(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    mock_driver.get_tp_positions.return_value = {
        'A': 10000, 'B': 0, 'C': 5000, 'D': 4000, 'E': 18000, 'F': -4500
    }
    robot.update_positions()

    assert robot.robot_pos['X'] == pytest.approx(20.0)
    assert robot.robot_pos['Y'] == pytest.approx(-10.0)
    assert robot.robot_pos['Z'] == pytest.approx(10.0)
    assert robot.robot_pos['THETA'] == pytest.approx(90.0)
    assert robot.robot_pos['PHI'] == pytest.approx(45.0)

    # Re-vérification de la cinématique
    assert robot.capsule_pos['X'] == pytest.approx(20.0 - 60 * math.cos(math.radians(45)))
    assert robot.capsule_pos['Y'] == pytest.approx(-10.0 + 50.0)
    assert robot.capsule_pos['Z'] == pytest.approx(10.0 - 60 * math.sin(math.radians(45)))