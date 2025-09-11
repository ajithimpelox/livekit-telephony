import os
import mysql.connector.pooling
import mysql.connector
from dotenv import load_dotenv
from utils.common import logger

load_dotenv()

db_config = {
             "host":os.getenv("DB_HOST"),
             "database":os.getenv("DB_NAME"),
             "user":os.getenv("DB_USER"),
             "password":os.getenv("DB_PASS")
        }

def get_db_connection():
    try:
        dbconfig = db_config
        return mysql.connector.pooling.MySQLConnectionPool(pool_name = "db_connections", pool_size = 30,pool_reset_session=True, **dbconfig)

    except Exception as err:
        logger.error("Cannot connect to db {}".format(err))
        return None


def check_connection():
    return True

class ConnectionPool:
    def __init__(self):
        self.db_config = self.get_config()
    
    def get_config(self):
        try:
            return  db_config

        except Exception as err:
            logger.error("Exception while getting DB Config {}".format(err))
            return None
    
    def get_connection(self):
        try:
            conn = mysql.connector.connect(
                                            host=self.db_config['host'],
                                            user=self.db_config['user'],
                                            password=self.db_config['password'],
                                            database=self.db_config['database']
                                            )
            return conn
        except Exception as err:
            logger.error("DBMGR-101 Exception while creating Database connection {}".format(err))
            return None
            
connection_pool = ConnectionPool()
