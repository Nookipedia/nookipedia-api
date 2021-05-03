# nookipedia-api
The Nookipedia API is a free RESTful service provides endpoints for retrieving Animal Crossing data pulled from the [Nookipedia wiki](https://nookipedia.com/wiki/Main_Page), the largest community-driven encyclopedia about the series. Built using Python and [Flask](https://flask.palletsprojects.com/en/1.1.x/), the key benefit of using this API is access to clean structured data spanning the entire Animal Crossing series, pulled from information that is constantly updated and expanding as editors work on the wiki. 

Visit https://api.nookipedia.com/ for more information.

## Support
Our primary method of supporting users and developers is through the [Nookipedia Discord](https://nookipedia.com/wiki/Nookipedia:Discord); API users and contributors are granted access to the private #wiki-api channel where they can participate in a community of practice and receive near round-the-clock support.

You may also [open an issue](https://github.com/Nookipedia/nookipedia-api/issues/new) here on GitHub if you need help, would like to request a feature, or have a bug to report.

## Contributing
Anyone is welcome and encouraged to contribute to this API!

See the [contributing guide](CONTRIBUTING.md) for full details and guidance.

## Technical Overview
Nookipedia, which runs on the MediaWiki wiki software (same as Wikipedia), utilizes the [Cargo](https://www.mediawiki.org/wiki/Extension:Cargo) extension. Cargo lets editors store data from templates in structured databases. For example, if you visit any villager's article on Nookipedia (e.g. [Rosie](https://nookipedia.com/wiki/Rosie)), there is an infobox at the top-right of the page; all that information as defined in the infobox is also stored in a database on the backend so that it can be queried elsewhere on the wiki, or externally by third parties. See Nookipedia's [Project Database](https://nookipedia.com/wiki/Nookipedia:Project_Database) for more information.

This API is essentially a wrapper for the MediaWiki Cargo API that comes as part of the extension. See the [MediaWiki cargoquery endpoint](https://nookipedia.com/w/api.php?action=help&modules=cargoquery) for how Cargo tables can be queried directly.

While the Cargo API is freely available for querying, we have our custom-built API for the following reasons:
* Far simpler endpoints.
  * Nookipedia API way: https://api.nookipedia.com/nh/fish/sea_bass
  * Cargo way: https://nookipedia.com/w/api.php?action=cargoquery&format=json&limit=200&tables=nh_fish&fields=name%2Cnumber%2Cimage%2Ccatchphrase%2Ccatchphrase2%2Cn_availability%2Cn_m1%2Cn_m2%2Cn_m3%2Cn_m4%2Cn_m5%2Cn_m6%2Cn_m7%2Cn_m8%2Cn_m9%2Cn_m10%2Cn_m11%2Cn_m12%2Cs_availability%2Cs_m1%2Cs_m2%2Cs_m3%2Cs_m4%2Cs_m5%2Cs_m6%2Cs_m7%2Cs_m8%2Cs_m9%2Cs_m10%2Cs_m11%2Cs_m12%2Ctime%2Clocation%2Cshadow_size%2Crarity%2Ctotal_catch%2Csell_nook%2Csell_cj%2Ctank_width%2Ctank_length&where=name=%27sea%20bass%27
* Hosted on its own dedicated server, so it is highly scalable and not subject to the wiki's performance limitations or downtime.
* Changes Nookipedia makes to its Cargo tables will be reflected in this API, so users can trust that nothing will break as Nookipedia's tables evolve.
* Returns from the Cargo API are cleaned up, simplified, and restructured as needed.
* Caching policies that we can adjust as needed.
* Additional features built in, such as the ability to generate thumbnails of varying size.
* Actively monitored and under development (your feature requests can come to life).

## Deployment
This application requires Python 3 and [venv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/).

This application has the following dependencies from `apt get`:
* `software-properties-common`
* `memcached`
* `libmemcached-dev`
* `sqlite3`

Before running this application:

* Create a virtual environment by running `python3 -m venv env && source env/bin/activate`.
  Check if this is successful if `(env)` is added at the beginning of your prompt.
  * For those running csh or fish instead of the default shell,
    replace `activate` with `activate.csh` or `activate.fish`.
* Install the requirements of the project by running `pip install -r requirements.txt`
* Create the database for storing admin/client secrets.
  Replace `<>` values with your desired values.
  Note that the API requires a UUID key (`<uuid>`) to make calls

```
$ sudo sqlite3 <desired_db_name>.db
sqlite3> CREATE TABLE <keys_table_name> ( key varchar(32), email TEXT, project TEXT );
sqlite3> CREATE TABLE <admin_keys_table_name> ( key varchar(32) );
sqlite3> INSERT INTO <keys_table_name> VALUES ( "<uuid>", "test", "test" );
sqlite3> .exit 0;
```

* In `config.ini`:
  * Fill in the `SECRET_KEY` with a long random string of bytes (used for securely signing the session cookie; [learn more](https://flask.palletsprojects.com/en/1.1.x/config/#SECRET_KEY))
  * Fill in the names for the `DATABASE`, `DB_KEYS`, and `DB_ADMIN_KEYS`
    with `<desired_db_name>.db`, `<keys_table_name>`, and `<admin_keys_table_name>` (fill in values respective to what was used to instantiate the database above)
  * The AUTH section is optional. Nookipedia bot-owners and administrators may authenticate into the wiki to enable higher query limits by generating a username and password at Special:BotPasswords.
* In `dashboard-config.cfg`, change the dashboard's password to something other than the default `admin`.

### Local / Dev
`flask run --host=0.0.0.0`. Easy.

Note that Flask's built-in server is _not_ suitable for production.

### Production
There are a variety of options out there for setting up a proper production server (cloud services, Gunicorn, uWSGI, etc.). Visit [Flask's deployment page](https://flask.palletsprojects.com/en/1.1.x/deploying/) for a list of options.

Nookipedia's API is deployed via uWSGI and nginx. If you'd like to set up something similar and need help, feel free to get in touch.

## Licensing
The Nookipedia API codebase is licensed under the MIT license. See [license file](LICENSE) for full text.

Dependencies are copyright their respective authors and used under their respective licenses.
* [ReDoc](https://github.com/Redocly/redoc), [MIT License](https://github.com/Redocly/redoc/blob/master/LICENSE), Copyright (c) 2015-present, Rebilly, Inc. 
* [Font Awesome Free 5.14.0](https://fontawesome.com), [Font Awesome Free License](https://fontawesome.com/license/free)
  * Icons — CC BY 4.0 License
  * Fonts — SIL OFL 1.1 License
  * Code — MIT License
