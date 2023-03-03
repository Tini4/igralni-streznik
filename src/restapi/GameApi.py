# -*- coding: utf-8 -*-
import importlib
import logging
from multiprocessing import freeze_support
from queue import Queue
from typing import Dict

from flask import Flask, jsonify
from flask_restx import Resource, Api, fields
from gevent.pywsgi import WSGIServer

from src.servers.GameServer import GameServer
from src.servers.StateServer import StateServer
from src.servers.TrackerServer import TrackerServer
from src.utils import read_config, create_logger


class GameApi:
    def __init__(self, game_name: str):
        freeze_support()
        self.game_config: dict = read_config(f'./src/games/{game_name.lower()}/game_config.yaml')

        logger = create_logger(logging.getLevelName(self.game_config['log_level']))
        logger.info('Started')

        self.game_name: str = game_name.capitalize()
        self.GameClass = getattr(
            importlib.import_module(f"src.games.{self.game_name.lower()}.{self.game_name}"),
            self.game_name
        )

        self.game_servers: Dict[str, GameServer] = {}
        self.server_queue: Queue = Queue()

        self.tracker_server = TrackerServer()
        self.tracker_server.start()

        self.state_server: StateServer = StateServer(self.tracker_server, self.game_config)
        self.state_server.start()

        self.rest_server = WSGIServer(('0.0.0.0', 8088), create_api(self))

    def start(self):
        self.rest_server.serve_forever()

    def create_game_server(self, team_1, team_2, game_id=None) -> GameServer:
        new_game = self.GameClass(self.state_server, self.game_config, team_1, team_2)
        new_game.start()

        if game_id is not None:
            new_game.id = game_id

        self.server_queue.put(new_game.id)
        self.game_servers[new_game.id] = new_game

        # TODO: This needs to be changed.
        if len(self.game_servers) >= 50:
            self.game_servers.pop(self.server_queue.get())

        return new_game

    def start_test_game_server(self) -> GameServer:
        team_ids = list(self.game_config['robots'].keys())
        team_1 = team_ids[0]
        team_2 = team_ids[1]

        test_game_server = self.create_game_server(team_1, team_2, 'test')
        test_game_server.game_time = 99999
        test_game_server.start_game()

        return test_game_server


def create_api(game_api: GameApi):
    app = Flask(__name__, instance_relative_config=True)
    api = Api(app,
              version='1.0',
              title='Robo liga API',
              description='A simple API for Robo Liga games.'
              )

    game_ns = api.namespace('game', description='Game operations')
    team_ns = api.namespace('team', description='Team operations')

    @game_ns.route('/')
    class GameList(Resource):

        @game_ns.expect(api.model('CreateGame', {
            'team_1': fields.Integer(required=True, description='Team 1 ID'),
            'team_2': fields.Integer(required=True, description='Team 2 ID'),
        }))
        @game_ns.response(200, "Success", fields.String)
        def post(self):
            """
            Create a new game
            """
            try:
                team_1 = int(api.payload['team_1'])
                team_2 = int(api.payload['team_2'])

                new_game = game_api.create_game_server(team_1, team_2)
                return new_game.id

            except Exception as e:
                api.abort(500, f"Unknown error occurred: {e}")

        @game_ns.response(200, "Success", fields.List(fields.String))
        def get(self):
            """
            List all games
            """
            games = [game_id for game_id in game_api.game_servers.keys()]
            return jsonify(games)

    @game_ns.route('/<string:game_id>')
    @game_ns.response(404, 'Game not found')
    @game_ns.param('game_id', 'The game identifier')
    class Game(Resource):
        @game_ns.response(200, "Success", game_api.GameClass.to_model(api, game_api.game_config))
        def get(self, game_id):
            """
            Fetch a game
            """
            if game_id in game_api.game_servers:
                return game_api.game_servers[game_id].to_json()
            else:
                api.abort(404, f"Game with id {game_id} doesn't exist")

    @game_ns.route('/<string:game_id>/score')
    @game_ns.response(404, 'Game not found')
    @game_ns.param('game_id', 'The game identifier')
    class GameScore(Resource):
        alter_score_model = api.model('AlterScore', {
            'team_1': fields.Integer(required=True, description='Team 1 ID'),
            'team_2': fields.Integer(required=True, description='Team 2 ID'),
        })

        @game_ns.expect(alter_score_model)
        @game_ns.response(200, "Success", game_api.GameClass.to_model(api, game_api.game_config))
        def put(self, game_id):
            """
            Alter score of the game
            """
            if game_id in game_api.game_servers:
                game_server = game_api.game_servers[game_id]
                game_server.alter_score(api.payload['team_1'], api.payload['team_2'])
                return game_server.to_json()
            else:
                api.abort(404, f"Game with id {game_id} doesn't exist")

    @game_ns.route('/<string:game_id>/start')
    @game_ns.response(404, 'Game not found')
    @game_ns.param('game_id', 'The game identifier')
    class GameStart(Resource):

        @game_ns.response(200, "Success", game_api.GameClass.to_model(api, game_api.game_config))
        def put(self, game_id):
            """
            Start the game
            """
            if game_id in game_api.game_servers:
                game_server = game_api.game_servers[game_id]
                game_server.start_game()
                return game_server.to_json()
            else:
                api.abort(404, f"Game with id {game_id} doesn't exist")

    @game_ns.route('/<string:game_id>/stop')
    @game_ns.response(404, 'Game not found')
    @game_ns.param('game_id', 'The game identifier')
    class GameStop(Resource):
        @game_ns.response(200, "Success", game_api.GameClass.to_model(api, game_api.game_config))
        def put(self, game_id):
            """
            Stop the game
            """
            if game_id in game_api.game_servers:
                game_server = game_api.game_servers[game_id]
                game_server.game_on = False
                return game_server.to_json()
            else:
                api.abort(404, f"Game with id {game_id} doesn't exist")

    @game_ns.route('/<string:game_id>/time')
    @game_ns.response(404, 'Game not found')
    @game_ns.param('game_id', 'The game identifier')
    class GameTime(Resource):
        @game_ns.expect(api.model('SetTime', {
            'game_time': fields.Integer(required=True, description='Game time in seconds'),
        }))
        @game_ns.response(200, "Success", game_api.GameClass.to_model(api, game_api.game_config))
        def put(self, game_id):
            """
            Set game time
            """
            if game_id in game_api.game_servers:
                game_server = game_api.game_servers[game_id]
                game_server.set_game_time(api.payload['game_time'])
                return game_server.to_json()
            else:
                api.abort(404, f"Game with id {game_id} doesn't exist")

    @game_ns.route('/<string:game_id>/teams')
    @game_ns.response(404, 'Game not found')
    @game_ns.param('game_id', 'The game identifier')
    class GameTeams(Resource):
        @game_ns.expect(api.model('SetTeams', {
            'team_1': fields.Integer(required=True, description='Team 1 ID'),
            'team_2': fields.Integer(required=True, description='Team 2 ID'),
        }))
        @game_ns.response(200, "Success", game_api.GameClass.to_model(api, game_api.game_config))
        def put(self, game_id):
            """
            Set teams
            """
            if game_id in game_api.game_servers:
                game_server = game_api.game_servers[game_id]
                game_server.set_teams(api.payload['team_1'], api.payload['team_2'])
                return game_server.to_json()
            else:
                api.abort(404, f"Game with id {game_id} doesn't exist")

    @game_ns.route('/<string:game_id>/pause')
    @game_ns.response(404, 'Game not found')
    @game_ns.param('game_id', 'The game identifier')
    class GamePause(Resource):
        @game_ns.response(200, "Success", game_api.GameClass.to_model(api, game_api.game_config))
        def put(self, game_id):
            """
            Pause or unpause the game
            """
            if game_id in game_api.game_servers:
                game_server = game_api.game_servers[game_id]
                game_server.pause_game()
                return game_server.to_json()
            else:
                api.abort(404, f"Game with id {game_id} doesn't exist")

    @team_ns.route('/')
    class Teams(Resource):
        team_model = api.model('TeamIdName', {
            'id': fields.Integer(required=True, description='Team ID'),
            'name': fields.String(required=True, description='Team name'),
        })

        @team_ns.response(200, 'Success', fields.List(fields.Nested(team_model)))
        def get(self):
            """
            Get list of teams
            """
            return jsonify(
                [{"id": teamId, "name": teamName} for teamId, teamName in game_api.game_config['robots'].items()],
                ensure_ascii=False
            )

    return app
