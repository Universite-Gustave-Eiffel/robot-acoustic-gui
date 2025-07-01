# tests/test_robot_controller.py
import pytest
from unittest.mock import MagicMock
import configparser
import math

# Ajustez l'import pour qu'il corresponde à votre structure
from src.controller_interface.GalilDriver import RobotController, GalilDriver, AXES_ORDER


@pytest.fixture(scope="module")
def test_config():
    """Crée un objet de configuration en mémoire pour les tests."""
    config = configparser.ConfigParser()
    config['RATIOS'] = {'x': '500', 'y': '-500', 'z': '400', 'theta': '200', 'phi': '-100'}
    # CORRECTION : Ajout des clés manquantes
    config['OFFSETS'] = {
        'correction_theta_x': '50.0',
        'correction_theta_y': '40.0',  # Valeur de test
        'correction_theta_z': '10.0',  # Valeur de test
        'correction_phi_l': '60.0'
    }
    return config


@pytest.fixture
def robot_with_mock_driver(test_config, mocker):
    """Crée une instance de RobotController avec un driver simulé."""
    mock_driver = MagicMock(spec=GalilDriver)

    # On passe directement l'objet config de test au constructeur
    robot = RobotController(mock_driver, test_config)
    return robot, mock_driver


# --- Les Tests ---

def test_conversion_mm_to_steps(robot_with_mock_driver):
    robot, _ = robot_with_mock_driver
    assert robot._to_steps('X', 10) == 5000
    assert robot._to_steps('Y', -20) == 10000


def test_conversion_degrees_to_steps(robot_with_mock_driver):
    robot, _ = robot_with_mock_driver
    assert robot._to_steps('THETA', 90) == 18000
    assert robot._to_steps('PHI', -45) == 4500


def test_move_to_single_axis(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    robot.move_to(X=10)
    mock_driver.send_cmd.assert_any_call("PA 5000,,,,,")
    mock_driver.send_cmd.assert_any_call("BG AB")
    mock_driver.wait_motion_complete.assert_called_with("AB")


def test_move_to_multiple_axes(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    robot.move_to(Y=-20, Z=5, PHI=10)
    mock_driver.send_cmd.assert_any_call("PA ,,10000,2000,,-1000")
    mock_driver.send_cmd.assert_any_call("BG CDF")
    mock_driver.wait_motion_complete.assert_called_with("CDF")


def test_go_home(robot_with_mock_driver):
    robot, mock_driver = robot_with_mock_driver
    robot.go_home()
    mock_driver.send_cmd.assert_any_call("PA 0,,0,0,0,0")
    mock_driver.send_cmd.assert_any_call("BG ABCDEF")
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

    # Vérification de la cinématique (theta=90, phi=45)
    # x_p = 20 + (50*cos(90)) - (40*sin(90)) = 20 - 40 = -20
    # y_p = -10 + (50*sin(90)) + (40*cos(90)) = -10 + 50 = 40
    # z_p = 10 + 10 - (60*sin(45)) = 20 - 42.42 = -22.42
    assert robot.capsule_pos['X'] == pytest.approx(-20.0)
    assert robot.capsule_pos['Y'] == pytest.approx(40.0)
    assert robot.capsule_pos['Z'] == pytest.approx(-22.42, abs=0.1)