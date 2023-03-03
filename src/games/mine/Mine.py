import logging
from typing import Dict, List

from flask_restx import Api, fields

from sledilnik.classes.ObjectTracker import ObjectTracker
from src.games.mine.MineTeam import MineTeam
from src.servers.GameServer import GameServer
from src.utils import check_if_object_in_area


class Mine(GameServer):
    def __init__(self, state_server, game_config, teams: List[int]):
        GameServer.__init__(self, state_server, game_config, teams)
        self.logger = logging.getLogger('games.Mine')
        self.charging_stations = {
            1: None,
            2: None
        }

    def init_team(self, robot_id: int, color: str):
        if robot_id in self.config['robots']:
            new_team = MineTeam(robot_id, color, self.config['robots'][robot_id], self.config['robot_time'])
            return new_team
        else:
            logging.error("Team with specified id does not exist in config!")
            raise Exception("Team with specified id does not exist in config!")

    def start_game(self):
        for team in self.teams.values():
            team.timer.start()

        super().start_game()

    def pause_game(self):
        for team in self.teams.values():
            team.timer.pause()

        super().pause_game()

    def resume_game(self):
        for team in self.teams.values():
            team.timer.resume()

        super().resume_game()

    def update_game_state(self):
        self.check_charging_stations()
        self.compute_score()

    def check_charging_stations(self):
        for team in self.teams.values():
            if team.robot_id in self.state_data.robots:
                robot = self.state_data.robots[team.robot_id]
                if check_if_object_in_area(robot.position, self.state_data.fields['charging_station_1']) and \
                        (self.charging_stations[1] is None or self.charging_stations[1] == robot.id):
                    self.teams[robot.id].charge(self.config['charging_time'])
                    self.charging_stations[1] = robot.id
                elif check_if_object_in_area(robot.position, self.state_data.fields['charging_station_2']) and \
                        (self.charging_stations[2] is None or self.charging_stations[2] == robot.id):
                    self.teams[robot.id].charge(self.config['charging_time'])
                    self.charging_stations[2] = robot.id
                else:
                    if self.charging_stations[1] == robot.id:
                        self.charging_stations[1] = None
                    elif self.charging_stations[2] == robot.id:
                        self.charging_stations[2] = None
                    self.teams[robot.id].stop_charging()

    def compute_score(self):

        scores = {}

        for good_ore in self.state_data.objects['good_ore'].values():
            for team in self.teams.values():
                if check_if_object_in_area(good_ore.position, self.state_data.fields[f'{team.color}_basket']):
                    scores[team.robot_id] = self.config['points']['good']

        for bad_ore in self.state_data.objects['bad_ore'].values():
            for team in self.teams.values():
                if check_if_object_in_area(bad_ore.position, self.state_data.fields[f'{team.color}_basket']):
                    scores[team.robot_id] = self.config['points']['bad']

        for team in self.teams.values():
            team.score = scores.get(team.robot_id, 0)

    def to_json(self):
        result = super().to_json()
        merged_objects = {}
        for ot in result['objects'].values():
            merged_objects.update(ot)

        result['objects'] = merged_objects
        return result

    @classmethod
    def to_model(cls, api: Api, game_config: Dict):
        result = super().to_model(api, game_config)
        result['objects'] = fields.Nested(
            api.model('Objects', {
                str(o): fields.Nested(
                    ObjectTracker.to_model(api),
                    required=False
                )
                for ot in game_config['objects']
                for o in game_config['objects'][ot]

            })
        )
        result['teams'] = fields.Nested(api.model(
            'Teams',
            {str(t): fields.Nested(MineTeam.to_model(api)) for t in game_config['robots']})
        )
        return result
