from .AAA3A_utils import CogsUtils  # isort:skip
from redbot.core.bot import Red  # isort:skip
from redbot.core.utils import get_end_user_data_statement

from .cmdchannel import CmdChannel

__red_end_user_data_statement__ = get_end_user_data_statement(file=__file__)


async def setup(bot: Red):
    cog = CmdChannel(bot)
    await CogsUtils().add_cog(bot, cog)
