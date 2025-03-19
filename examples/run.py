# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
# web_toolkit.py start
import datetime
import io
import json
import os
import random
import re
import shutil
import time
from copy import deepcopy
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Dict,
    List,
    Optional,
    Tuple,
    TypedDict,
    Union,
    cast,
)

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from camel.agents import ChatAgent
from camel.logger import get_logger
from camel.messages import BaseMessage
from camel.models import BaseModelBackend, ModelFactory
from camel.toolkits import FunctionTool, VideoAnalysisToolkit
from camel.toolkits.base import BaseToolkit
from camel.types import ModelPlatformType, ModelType
from camel.utils import dependencies_required, retry_on_error
# web_toolkit.py end



from dotenv import load_dotenv
from camel.models import ModelFactory
from camel.toolkits import (
    AudioAnalysisToolkit,
    CodeExecutionToolkit,
    ExcelToolkit,
    ImageAnalysisToolkit,
    SearchToolkit,
    VideoAnalysisToolkit,
    BrowserToolkit,
    FileWriteToolkit,
)
from camel.toolkits.web_toolkit import _reload_image, _parse_json_output
from camel.toolkits.web_toolkit import *
from camel.types import ModelPlatformType, ModelType
from camel.logger import set_log_level
from camel.societies import RolePlaying

from owl.utils import run_society, DocumentProcessingToolkit

import pathlib

base_dir = pathlib.Path(__file__).parent.parent
env_path = base_dir / "owl" / ".env"
load_dotenv(dotenv_path=str(env_path))

set_log_level(level="DEBUG")


class CustomWebToolkit(WebToolkit):
    def _observe(
        self, task_prompt: str, detailed_plan: Optional[str] = None
                    ) -> Tuple[str, str, str]:
        r"""Let agent observe the current environment, and get the next action."""

        detailed_plan_prompt = ""

        if detailed_plan is not None:
            detailed_plan_prompt = f"""
    Here is a plan about how to solve the task step-by-step which you must follow: 
    <detailed_plan>{detailed_plan}<detailed_plan>
        """

        observe_prompt = f"""
    Please act as a web agent to help me complete the following high-level task: 
    <task>{task_prompt}</task>
    Now, I have made screenshot (only the current viewport, not the full webpage) 
    based on the current browser state, and marked interactive elements in the 
    webpage.
    Please carefully examine the requirements of the task, and current state of 
    the browser, and provide the next appropriate action to take.

    {detailed_plan_prompt}

    Here are the current available browser functions you can use:
    {AVAILABLE_ACTIONS_PROMPT}

    NOTE: 注意搜索文本框往往紧邻着搜索按钮, 如果搜索按钮id是80,你要优先考虑79为搜索文本框.

    Here are the latest {self.history_window} trajectory (at most) you have taken:
    <history>
    {self.history[-self.history_window:]}
    </history>

    Your output should be in json format, including the following fields:
    - `observation`: 你需要记录当前页面的具体重要信息,例如商品名,商品价格,具体商品信息等,商品特点可以参考商品图标描述.这些信息会在后面步骤进行分析和比较.The detailed image description about the current viewport. Do 
    not over-confident about the correctness of the history actions. You should 
    always check the current viewport to make sure the correctness of the next 
    action.
    - `reasoning`: The reasoning about the next action you want to take, and the 
    possible obstacles you may encounter, and how to solve them. Do not forget to 
    check the history actions to avoid the same mistakes, 注意fill_input_id()的文本框必须是个文本框,
    不要进行添加购物车等操作, 你只需要进行信息采集即可.
    - `action_code`: The action code you want to take. It is only one step action 
    code, without any other texts (such as annotation)

    Here are an example of the output:
    ```json
    {{
    "observation": [IMAGE_DESCRIPTION],
    "reasoning": [YOUR_REASONING],
    "action_code": "fill_input_id([ID], [TEXT])"
    }}

    Here are some tips for you:
    - Never forget the overall question: **{task_prompt}**
    - Maybe after a certain operation (e.g. click_id), the page content has not 
    changed. You can check whether the action step is successful by looking at the 
    `success` of the action step in the history. If successful, it means that the 
    page content is indeed the same after the click. You need to try other methods.
    - If using one way to solve the problem is not successful, try other ways. 
    Make sure your provided ID is correct!
    - Some cases are very complex and need to be achieve by an iterative process. 
    You can use the `back()` function to go back to the previous page to try other 
    methods.
    - There are many links on the page, which may be useful for solving the 
    problem. You can use the `click_id()` function to click on the link to see if 
    it is useful.
    - Always keep in mind that your action must be based on the ID shown in the 
    current image or viewport, not the ID shown in the history.
    - If the webpage needs human verification, you must avoid processing it. 
    Please use `back()` to go back to the previous page, and try other ways.
    - If you have tried everything and still cannot resolve the issue, please stop 
    the simulation, and report issues you have encountered.
    - Check the history actions carefully, detect whether you have repeatedly made 
    the same actions or not.
    - When dealing with wikipedia revision history related tasks, you need to 
    think about the solution flexibly. First, adjust the browsing history 
    displayed on a single page to the maximum, and then make use of the 
    find_text_on_page function. This is extremely useful which can quickly locate 
    the text you want to find and skip massive amount of useless information.
    - Flexibly use interactive elements like slide down selection bar to filter 
    out the information you need. Sometimes they are extremely useful.
    ```
        """

        # get current state
        som_screenshot, som_screenshot_path = self.browser.get_som_screenshot(
            save_image=True
        )
        img = _reload_image(som_screenshot)
        message = BaseMessage.make_user_message(
            role_name='user', content=observe_prompt, image_list=[img]
        )
        resp = self.web_agent.step(message)

        resp_content = resp.msgs[0].content

        resp_dict = _parse_json_output(resp_content)
        observation_result: str = resp_dict.get("observation", "")
        reasoning_result: str = resp_dict.get("reasoning", "")
        action_code: str = resp_dict.get("action_code", "")

        if action_code and "(" in action_code and ")" not in action_code:
            action_match = re.search(
                r'"action_code"\s*:\s*[`"]([^`"]*\([^)]*\))[`"]', resp_content
            )
            if action_match:
                action_code = action_match.group(1)
            else:
                logger.warning(
                    f"Incomplete action_code detected: {action_code}"
                )
                if action_code.startswith("fill_input_id("):
                    parts = action_code.split(",", 1)
                    if len(parts) > 1:
                        id_part = (
                            parts[0].replace("fill_input_id(", "").strip()
                        )
                        action_code = f"fill_input_id({id_part}, 'Please fill the text here.')"

        action_code = action_code.replace("`", "").strip()

        return observation_result, reasoning_result, action_code


    def click_id(self, identifier: Union[str, int]):
        if isinstance(identifier, int):
            identifier = str(identifier)
        target = self.page.locator(f"[__elementId='{identifier}']")

        try:
            target.wait_for(timeout=5000)
        except (TimeoutError, Exception) as e:
            logger.debug(f"Error during click operation: {e}")
            raise ValueError("No such element.") from None

        target.scroll_into_view_if_needed()

        new_page = None
        try:
            with self.page.expect_event("popup", timeout=2000) as page_info:
                box = cast(Dict[str, Union[int, float]], target.bounding_box())
                self.page.mouse.click(
                    box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                )
                new_page = page_info.value

                # If a new page is opened, switch to it
                if new_page:
                    self.page_history.append(deepcopy(self.page.url))
                    self.page = new_page

        except (TimeoutError, Exception) as e:
            logger.debug(f"Error during click operation: {e}")
            pass

        self._wait_for_load()


    def _initialize_agent(self) -> Tuple["ChatAgent", "ChatAgent"]:
        r"""Initialize the agent."""
        from camel.agents import ChatAgent

        if self.web_agent_model is None:
            web_agent_model = ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI,
                model_type=ModelType.GPT_4O,
                model_config_dict={"temperature": 0, "top_p": 1},
            )
        else:
            web_agent_model = self.web_agent_model

        if self.planning_agent_model is None:
            planning_model = ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI,
                model_type=ModelType.O3_MINI,
            )
        else:
            planning_model = self.planning_agent_model

        system_prompt = """
You are a helpful web agent that can assist users in browsing the web.
Given a high-level task, you can leverage predefined browser tools to help 
users achieve their goals.
        """

        web_agent = ChatAgent(
            system_message=system_prompt,
            model=web_agent_model,
            output_language=self.output_language,
        )

        planning_system_prompt = """
You are a helpful planning agent that can assist users in planning complex 
tasks which need multi-step browser interaction.
        """

        planning_agent = ChatAgent(
            system_message=planning_system_prompt,
            model=planning_model,
            output_language=self.output_language,
        )

        return web_agent, planning_agent

    def _get_final_answer(self, task_prompt: str) -> str:
        r"""Get the final answer based on the task prompt and current browser state.
        It is used when the agent thinks that the task can be completed without any further action, and answer can be directly found in the current viewport.
        """

        prompt = f"""
We are solving a complex web task which needs multi-step browser interaction. After the multi-step observation, reasoning and acting with web browser, we think that the task is currently solved.
Here are all trajectory we have taken:
<history>{self.history}</history>
Please find the final answer, or give valuable insights and founds (e.g. if previous actions contain downloading files, your output should include the path of the downloaded file) about the overall task: <task>{task_prompt}</task>
        """

        message = BaseMessage.make_user_message(
            role_name='user',
            content=prompt,
        )

        print(f"\033[92m------------------------------{message}\033[0m")  # Print message in green

        resp = self.web_agent.step(message)
        return resp.msgs[0].content


    def _task_replanning(
        self, task_prompt: str, detailed_plan: str
    ) -> Tuple[bool, str]:
        r"""Replan the task based on the given task prompt.

        Args:
            task_prompt (str): The original task prompt.
            detailed_plan (str): The detailed plan to replan.

        Returns:
            Tuple[bool, str]: A tuple containing a boolean indicating whether the task needs to be replanned, and the replanned schema.
        """

        # Here are the available browser functions we can use: {AVAILABLE_ACTIONS_PROMPT}
        replanning_prompt = f"""
We are using browser interaction to solve a complex task which needs multi-step actions.
Here are the overall task:
<overall_task>{task_prompt}</overall_task>

In order to solve the task, we made a detailed plan previously. Here is the detailed plan:
<detailed plan>{detailed_plan}</detailed plan>

According to the task above, we have made a series of observations, reasonings, and actions. Here are the latest {self.history_window} trajectory (at most) we have taken:
<history>{self.history[-self.history_window:]}</history>

However, the task is not completed yet. As the task is partially observable, we may need to replan the task based on the current state of the browser if necessary.
如果历史规划任务已经可以回答当前任务, 则不需要重新规划方案, 否则请提供一个新的规划方案.

Your output should be in json format, including the following fields:
- `if_need_replan`: bool, A boolean value indicating whether the task needs to be fundamentally replanned.
- `replanned_schema`: str, The replanned schema for the task, which should not be changed too much compared with the original one. If the task does not need to be replanned, the value should be an empty string. 
"""
        resp = self.planning_agent.step(replanning_prompt)
        resp_dict = _parse_json_output(resp.msgs[0].content)

        if_need_replan = resp_dict.get("if_need_replan", False)
        replanned_schema = resp_dict.get("replanned_schema", "")

        if if_need_replan:
            return True, replanned_schema
        else:
            return False, replanned_schema


    @dependencies_required("playwright")
    def browser_simulation(
        self, task_prompt: str, start_url: str, round_limit: int = 12
    ) -> str:
        r"""A powerful toolkit which can simulate the browser interaction to solve the task which needs multi-step actions.

        Args:
            task_prompt (str): The task prompt to solve.
            start_url (str): The start URL to visit.
            round_limit (int): The round limit to solve the task (default: 12).

        Returns:
            str: The simulation result to the task.
        """

        self._reset()
        task_completed = False
        detailed_plan = self._task_planning(task_prompt, start_url)
        logger.debug(f"Detailed plan: {detailed_plan}")

        self.browser.init()
        self.browser.visit_page(start_url)

        for i in range(round_limit):
            observation, reasoning, action_code = self._observe(
                task_prompt, detailed_plan
            )
            logger.debug(f"Observation: {observation}")
            logger.debug(f"Reasoning: {reasoning}")
            logger.debug(f"Action code: {action_code}")

            if "stop" in action_code:
                task_completed = True
                trajectory_info = {
                    "round": i,
                    "observation": observation,
                    "thought": reasoning,
                    "action": action_code,
                    "action_if_success": True,
                    "info": None,
                    "current_url": self.browser.get_url(),
                }
                self.history.append(trajectory_info)
                break

            else:
                success, info = self._act(action_code)
                if not success:
                    logger.warning(f"Error while executing the action: {info}")

                trajectory_info = {
                    "round": i,
                    "observation": observation,
                    "thought": reasoning,
                    "action": action_code,
                    "action_if_success": success,
                    "info": info,
                    "current_url": self.browser.get_url(),
                }
                self.history.append(trajectory_info)

                # replan the task if necessary
                if_need_replan, replanned_schema = self._task_replanning(
                    task_prompt, detailed_plan
                )
                if if_need_replan:
                    detailed_plan = replanned_schema
                    logger.debug(f"Replanned schema: {replanned_schema}")

        if not task_completed:
            simulation_result = f"""
                The task is not completed within the round limit. Please check the last round {self.history_window} information to see if there is any useful information:
                <history>{self.history[-self.history_window:]}</history>
            """

        else:
            simulation_result = self._get_final_answer(task_prompt)

        # self.browser.close()
        return simulation_result







    def close(self):
        pass
        # self.browser.close()
        # self.playwright.stop()



    # def get_tools(self):
    #     # 自定义实现
    #     print("Using custom WebToolkit")
    #     tools = super().get_tools()  # 调用父类的实现（如果需要）
    #     # 在这里对 tools 进行修改或扩展
    #     return tools


def construct_society(question: str) -> OwlRolePlaying:
    r"""Construct a society of agents based on the given question.

    Args:
        question (str): The task or question to be addressed by the society.

    Returns:
        RolePlaying: A configured society of agents ready to address the question.
    """

    # Create models for different components
    models = {
        "user": ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O,
            model_config_dict={"temperature": 0},
        ),
        "assistant": ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O,
            model_config_dict={"temperature": 0},
        ),
        "web": ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O,
            model_config_dict={"temperature": 0},
        ),
        "planning": ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O,
            model_config_dict={"temperature": 0},
        ),
        "video": ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O,
            model_config_dict={"temperature": 0},
        ),
        "image": ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O,
            model_config_dict={"temperature": 0},
        ),
        "document": ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O,
            model_config_dict={"temperature": 0},
        ),
    }

    # Configure toolkits
    tools = [
        *CustomWebToolkit(
            headless=False,  # Set to True for headless mode (e.g., on remote servers)
            web_agent_model=models["web"],
            planning_agent_model=models["planning"],
        ).get_tools(),
        *VideoAnalysisToolkit(model=models["video"]).get_tools(),
        *AudioAnalysisToolkit().get_tools(),  # This requires OpenAI Key
        *CodeExecutionToolkit(sandbox="subprocess", verbose=True).get_tools(),
        *ImageAnalysisToolkit(model=models["image"]).get_tools(),
        SearchToolkit().search_duckduckgo,
        # SearchToolkit().search_google,  # Comment this out if you don't have google search
        SearchToolkit().search_wiki,
        *ExcelToolkit().get_tools(),
        *DocumentProcessingToolkit(model=models["document"]).get_tools(),
        *FileWriteToolkit(output_dir="./").get_tools(),
    ]

    # Configure agent roles and parameters
    user_agent_kwargs = {"model": models["user"]}
    assistant_agent_kwargs = {"model": models["assistant"], "tools": tools}

    # Configure task parameters
    task_kwargs = {
        "task_prompt": question,
        "with_task_specify": False,
    }

    # Create and return the society
    society = RolePlaying(
        **task_kwargs,
        user_role_name="user",
        user_agent_kwargs=user_agent_kwargs,
        assistant_role_name="assistant",
        assistant_agent_kwargs=assistant_agent_kwargs,
    )

    return society


def main():
    r"""Main function to run the OWL system with an example question."""
    # Example research question
    question = "去https://health.jd.com找三个适合孩子的感冒药, 然后进行价格的简单比较, 生成html表格"
    # question = "从这里https://www.weather.com.cn/weather/101010100.shtml, 查看北京今天的温度"

    # Construct and run the society
    society = construct_society(question)
    answer, chat_history, token_count = run_society(society)

    # Output the result
    print(f"\033[94mAnswer: {answer}\033[0m")


if __name__ == "__main__":
    main()
