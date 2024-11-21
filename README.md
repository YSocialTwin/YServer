![img_1.png](docs/Ysocial.png)

YSocial is a client-server application that implements a digital twin of a microblogging platform using Large Language Models (LLMs). This project simulates a social media-like environment where agents are represented by LLMs, allowing for realistic and efficient interactions.

This repository contains the code for the **server-side** of the application. 

The client-side code can be found [here](https://github.com/YSocialTwin/YClient)

For more information, please refer to the official [documentation](https://ysocialtwin.github.io/)

#### Features

- Realistic agent simulations using LLMs
- Microblogging platform with posting, commenting, and liking capabilities
- Client-server architecture for scalability and flexibility
- Support for various user interactions (e.g., posting, commenting, liking)
- Ability to simulate a wide range of scenarios and use cases

## Technical Details

![Schema](docs/schema.png)

- Programming Language: Python
- Framework: Flask + SQlite

## Getting Started

- Clone this repository to your local machine using git clone https://github.com/giuliorossetti/YServer.git
- Install dependencies for using pip install

### Usage

Set the server preferences modifying the file `config_files/exp_config.json`:

```json
{
  "name": "local_test",
  "host": "0.0.0.0",
  "port": 5010,
  "reset_db": "True",
  "modules": ["news", "voting"]
}
```
where:
- `name` is the name of the experiment (will be used to name the simulation database - which will be created under the folder `experiments`);
- `host` is the IP address of the server;
- `port` is the port of the server;
- `reset_db` is a flag to reset the database at each server start;
- `modules` is a list of additional modules to be loaded by the server (e.g., news, voting). Please note that the YClient must be configured to use the same modules.

Once the simulation is configured, start the YServer with the following command:

```bash
python y_server.py
```

#### Modules
- **News**: This module allows the server to access online news sources leveraging RSS feeds.
- **Voting**: This module allows the agents to cast their voting intention after interacting with peers contents (designed to perform political debate simulation).

## Contribution

Contributions are welcome! If you'd like to improve YSocial, please:

- Fork this repository
- Create a new branch for your feature or bug fix
- Submit a pull request with detailed changes and explanations

## Citation

If you use YSocial in your research, please cite the following paper:

```
@article{rossetti2024ysocial,
  title={Y Social: an LLM-powered microblogging Digital Twin},
  author={Rossetti, Giulio and Stella, Massimo and Cazabet, Rémy and 
  Abramski, Katherine and Cau, Erica and Citraro, Salvatore and 
  Failla, Andrea and Improta, Riccardo and Morini, Virginia and 
  Pansanella, Virginia},
  year={2024}
}
```

## License

YSocial is licensed under the GNU GENERAL PUBLIC LICENSEe. See LICENSE.txt for details.

