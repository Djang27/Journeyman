import random
from nba_api.stats.static import players
from nba_api.stats.endpoints import playercareerstats
import time
from unidecode import unidecode

def generatePlayer():

    playerList = players.get_active_players()
    gamePlayer = random.choice(playerList)
    return (gamePlayer["id"], unidecode(gamePlayer["full_name"]))

def getPlayerTeams():