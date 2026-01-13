import random
from nba_api.stats.static import players
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.static import teams  # module
import time
from unidecode import unidecode

def generatePlayer():
    playerList = players.get_active_players()
    gamePlayer = random.choice(playerList)
    return gamePlayer["id"], unidecode(gamePlayer["full_name"])

def getPlayerTeams(playerID):
    career = playercareerstats.PlayerCareerStats(player_id=playerID)
    playerStats = career.get_data_frames()[0]

    nba_teams_data = teams.get_teams()  
    team_dict = {team['id']: team['full_name'] for team in nba_teams_data}

    player_teams_list = []
    for team_id in playerStats["TEAM_ID"]:
        if team_id != 0 and team_id in team_dict:
            team_name = team_dict[team_id]
            if team_name not in player_teams_list:
                player_teams_list.append(team_name)

    time.sleep(1)
    return player_teams_list

def randomPlayer():
    while True:
        playerID, playerName = generatePlayer()
        teams_list = getPlayerTeams(playerID)
        if len(teams_list) > 1:
            break
    return playerName, teams_list
