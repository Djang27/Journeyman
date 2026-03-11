import random
from nba_api.stats.static import players
from nba_api.stats.endpoints import playercareerstats
from nba_api.stats.static import teams  
import time
from unidecode import unidecode

Headers = {
    "Host": "stats.nba.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:72.0) Gecko/20100101 Firefox/72.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Connection": "keep-alive",
    "Referer": "https://www.nba.com/",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}
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
    previous_team = None

    for team_id in playerStats["TEAM_ID"]:
        if team_id == 0 or team_id not in team_dict:
            continue
        
        current_team = team_dict[team_id].lower()
        
        if current_team != previous_team:
                player_teams_list.append(current_team)
                previous_team = current_team

    time.sleep(1)
    return player_teams_list

def randomPlayer():
    while True:
        player_ID, player_name = generatePlayer()
        teams_list = getPlayerTeams(player_ID)
        if len(teams_list) > 1:
            break
    return player_name, teams_list
