# Krampus
Krampus is a Python [sync server](https://northpole.dev/features/sync/) for [Santa](https://github.com/northpolesec/santa/). Krampus is written with modularity in mind, meaning the server can work with different database backends. Currently implemented are integrations for a Postgres, MySQL and Google Cloud Firestore.

For more information please read through [the wiki](https://github.com/kaiobendrauf/krampus/wiki).

## Getting Started

To get started with Krampus, you'll first need a database backend.
This is where rules and host configurations get stored when they are created.
For the backend, Krampus currently comes with support for Postgres, MySQL, and Google Cloud Firestore.
You can either run Postgres or MySQL yourself, or you can spin up a managed database instance in your cloud provider of choice.
We have provided [some examples in the wiki](https://github.com/kaiobendrauf/krampus/wiki/Example-Configurations) for setting up your database instance for a dev environment.

Once you've set up your database instance, you can setup Krampus.
Server configurations are described in detail [here](https://github.com/kaiobendrauf/krampus/wiki/Server-Configuration).
Most importantly, you must trigger the appropriate database module to be loaded with [environment variables](https://github.com/kaiobendrauf/krampus/wiki/Server-Configuration#Environment-Variables).
For example, if you use Postgres as your database backend, you should set [the `POSTGRES_*` environment variables](https://github.com/kaiobendrauf/krampus/wiki/Server-Configuration#postgres-specific-environment-variables) to configure how Krampus authenticating with your Postgres instance.
On first start, Krampus will create all of its relevant database tables.
Santa expects sync servers to be served over HTTPS, so when running Krampus you'll have to handle SSL termination by e.g. putting Krampus behind a reverse proxy like nginx, or Traefik.
For testing, you could use something like [ngrok](https://ngrok.com) to expose your test instance over HTTPS.

After you've got Krampus up and running behind HTTPS, you'll need to [configure how your Santa clients talk to Krampus](https://github.com/kaiobendrauf/krampus/wiki#santa-client-setup).
The bare minimum Santa configuration profile keys you'll need to set for Krampus are as follows:
```xml
<dict>
    <key>SyncBaseURL</key>
    <string>https://my.sync.server/</string>
</dict>
```
Although Krampus has some (modular) authentication options, Santa clients are limited in what authentication can be used. 
You can configure Krampus to authenticate clients via request headers, and set these in Santa with the `SyncExtraHeaders` configuration profile key.
However, the most secure approach is to let your reverse proxy or load balancer handle authentication via mTLS, as this offers a bit more security than a static secret that can leak and be re-used.

Finally, you can create [your configuration files](https://github.com/kaiobendrauf/krampus/wiki/Server-Configuration#postgres-specific-environment-variables), and use [`krampusctl`](https://github.com/kaiobendrauf/krampus/wiki/krampusctl) to create and update rules and host configurations on your Krampus instance!
With rules and host configurations now in the database, your clients will start picking up their configuration next time they sync with Krampus.
