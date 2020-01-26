# -*- coding: utf-8 -*-
import logging
from uuid import uuid1

import gevent

from so2.classes.GameLiveData import GameLiveData
from so2.servers.Server import Server
from so2.servers.StateServer import StateServer


class GameServer(Server):
    """Game state for particular game

    Pulls information from a state server and computers a game state.

    Attributes:
        id (UUID): Game id
        key (string): Key for write permissions
    """

    def __init__(self, state_server: StateServer):
        Server.__init__(self)
        self.logger = logging.getLogger('sledenje-objektom.GameServer')
        self.state_server = state_server
        self.id = uuid1()
        self.key = "very_secret_key"

    def _run(self):
        self.logger.info("Started a new game server with id: %s" % self.id)
        while True:
            # Wait for state server to update state
            self.state_server.updated.wait()
            # Update game from state

            self.gameData: GameLiveData = self.state_server.state

            gevent.sleep(0.01)
