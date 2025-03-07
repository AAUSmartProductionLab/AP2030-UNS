#include <iostream>
#include <string>
#include <random>
#include <thread>
#include <chrono>
#include <fstream>

#include <uuid/uuid.h>
#include <mqtt/async_client.h>
#include <nlohmann/json.hpp>
#include <nlohmann/json-schema.hpp>

using namespace std::chrono;
using nlohmann::json;
using nlohmann::json_schema::json_validator;

class Proxy;          // Forward declaration of the Proxy class
class RouterCallback; // Add this line

// Utility function to generate a random correlation ID
std::string generate_uuid()
{
    uuid_t uuid;
    char uuid_str[37];
    uuid_generate_random(uuid);
    uuid_unparse(uuid, uuid_str);
    return std::string(uuid_str);
}

// Function to load a JSON schema (mocked)
json load_schema(const std::string &schema_path)
{
    std::ifstream file(schema_path);

    if (!file) // Check the state of the file
    {
        std::cerr << "Couldn't open file\n";
        return 1;
    }
    return json::parse(file);
}

class RouterCallback : public mqtt::callback
{
private:
    struct Handler
    {
        std::string topic;
        std::function<void(const json &, mqtt::properties)> callback;
        json_validator *validator;
        json *schema;
    };
    std::vector<Handler> handlers_;

public:
    void message_arrived(mqtt::const_message_ptr msg) override
    {
        std::string topic = msg->get_topic();

        try
        {
            json payload = json::parse(msg->get_payload());
            mqtt::properties props = msg->get_properties();

            bool handled = false;
            for (const auto &handler : handlers_)
            {
                if (topic == handler.topic || topic.find(handler.topic) != std::string::npos)
                {
                    handler.callback(payload, props);
                    handled = true;
                }
            }

            if (!handled)
            {
                std::cout << "No handler found for topic: " << topic << std::endl;
            }
        }
        catch (const std::exception &e)
        {
            std::cerr << "Error processing message: " << e.what() << std::endl;
        }
    }

    void add_handler(const std::string &topic,
                     std::function<void(const json &, mqtt::properties)> callback,
                     json_validator *validator = nullptr,
                     json *schema = nullptr)
    {
        handlers_.push_back({topic, callback, validator, schema});
        std::cout << "Added handler for topic: " << topic << std::endl;
    }
};

class TopicCallback : public virtual mqtt::callback
{
    std::function<void(const json &, mqtt::properties)> callback_method_;
    json &sub_schema_;
    json_validator &sub_validator_;
    std::string &subtopic_;
    void message_arrived(mqtt::const_message_ptr msg) override
    {

        std::cout << "Message arrived on topic: " << msg->get_topic() << std::endl;

        std::cout << "Intended arrived on topic: " << subtopic_ << std::endl;

        // Only process messages for our specific subtopic
        if (msg->get_topic() != subtopic_)
        {
            std::cout << "Ignoring message for different topic" << std::endl;
            return;
        }
        json received_msg = json::parse(msg->get_payload());

        if (!sub_schema_.is_null())
        {
            sub_validator_.validate(received_msg);
        }
        if (callback_method_)
        {
            mqtt::properties props = msg->get_properties();
            callback_method_(received_msg, props);
        }
    }

public:
    TopicCallback(std::function<void(const json &, mqtt::properties)> callback_method, json_validator &validator, json &sub_schema, std::string &subtopic)
        : callback_method_(callback_method), sub_validator_(validator), sub_schema_(sub_schema), subtopic_(subtopic)
    {
    }
};

class Topic
{
protected:
    std::string pubtopic;
    std::string subtopic;
    int qos;
    json pub_schema;
    json sub_schema;
    json_validator pub_validator;
    json_validator sub_validator;
    std::function<void(const json &, mqtt::properties)> callback_method;
    std::unique_ptr<TopicCallback> callback_ptr_;

public:
    Topic(const std::string &topic, const std::string &publish_schema_path,
          const std::string &subscribe_schema_path, int qos,
          std::function<void(const json &, mqtt::properties)> callback_method)
        : qos(qos), callback_method(callback_method)
    {

        pub_schema = load_schema(publish_schema_path);
        sub_schema = load_schema(subscribe_schema_path);
        if (!pub_schema.is_null())
        {
            try
            {
                pub_validator.set_root_schema(pub_schema);
            }
            catch (const std::exception &e)
            {
                std::cerr << "Validation of schema failed, here is why: " << e.what() << "\n";
            }
            pubtopic = topic + pub_schema.value("subtopic", "");
        }
        else
        {
            pubtopic = topic;
        }

        if (!sub_schema.is_null())
        {
            sub_validator.set_root_schema(sub_schema);
            subtopic = topic + sub_schema.value("subtopic", "");
        }
        else
        {
            subtopic = topic;
        }
    }

    void publish(mqtt::async_client &client, const json &message)
    {
        try
        {

            if (!pub_schema.is_null())
            {

                pub_validator.validate(message);
            }
            std::string correlation_data = generate_uuid();
            mqtt::property correlation_property(mqtt::property::code::CORRELATION_DATA, correlation_data);
            mqtt::property response_topic(mqtt::property::code::RESPONSE_TOPIC, subtopic);
            mqtt::properties props;
            props.add(correlation_property);
            props.add(response_topic);

            if (!pubtopic.empty())
            {
                mqtt::message_ptr pubmsg = mqtt::make_message(pubtopic, message.dump(), qos, false, props);
                try
                {
                    client.publish(pubmsg)->wait_for(std::chrono::seconds(10));
                }
                catch (const mqtt::exception &exc)
                {
                    std::cerr << exc.what() << std::endl;
                    client.reconnect();
                }
            }
        }
        catch (std::exception &e)
        {
            std::cout << "Exception when setting up validating" << e.what() << std::endl;
            return;
        }
    }

    void subscribe(mqtt::async_client &client)
    {
        if (!subtopic.empty())
        {
            client.subscribe(subtopic, qos);
        }
    }
    void register_callback(Proxy &proxy);
};

class Response : public Topic
{
public:
    Response(std::string topic, std::string publish_schema_path,
             std::string subscribe_schema_path, int qos = 0,
             std::function<void(const json &, mqtt::properties)> callback_method = nullptr)
        : Topic(topic, publish_schema_path, subscribe_schema_path, qos, callback_method) {}

    void publish(mqtt::async_client &client, const json &request, mqtt::properties &props)
    {
        if (!pub_schema.is_null())
        {
            pub_validator.validate(request);
        }
        props.add(mqtt::property(mqtt::property::code::CORRELATION_DATA, generate_uuid()));
        try
        {
            std::string response_topic = mqtt::get<std::string>(props.get(mqtt::property::code::RESPONSE_TOPIC));
            client.publish(response_topic, request.dump(), qos, false, props);
        }
        catch (const std::exception &e)
        {
            // Handle the case where RESPONSE_TOPIC is not present
            std::cout << "Error: User Property RESPONSE_TOPIC not found, " << e.what() << std::endl;
        }
    }
};

class Request : public Topic
{
public:
    Request(std::string topic, std::string publish_schema_path,
            std::string subscribe_schema_path, int qos = 0,
            std::function<void(const json &, mqtt::properties)> callback_method = nullptr)
        : Topic(topic, publish_schema_path, subscribe_schema_path, qos, callback_method)
    {

        subtopic = pubtopic + sub_schema["subtopic"].get<std::string>() + "/" + generate_uuid();
    }
};

class Proxy : public mqtt::async_client
{
private:
    std::string &address;
    mqtt::connect_options &connOpts_;
    int &nretry_;
    std::shared_ptr<RouterCallback> router_;

public:
    Proxy(std::string &address, std::string &client_id, mqtt::connect_options &connOpts, int &nretry)
        : mqtt::async_client(address, client_id), address(address), connOpts_(connOpts), nretry_(nretry)
    {
        router_ = std::make_shared<RouterCallback>();
        set_callback(*router_);
        set_connected_handler([this](const std::string &)
                              { on_connect(); });
        set_disconnected_handler([this](const mqtt::properties &, mqtt::ReasonCode)
                                 { on_disconnect(); });
        set_connection_lost_handler([this](const std::string &cause)
                                    { on_connection_lost(cause); });
        connect(connOpts_)->wait();
        // #TODO this should idealy be in a calllback
    }
    void register_topic_handler(const std::string &topic,
                                std::function<void(const json &, mqtt::properties)> callback,
                                json_validator *validator = nullptr,
                                json *schema = nullptr)
    {
        router_->add_handler(topic, callback, validator, schema);
    }
    void on_connect()
    {
        std::cout << "Connected to broker " << address << std::endl;
    }

    void on_disconnect()
    {
        std::cout << "Disconnected from broker" << std::endl;
    }

    void on_connection_lost(const std::string &cause)
    {
        std::cout << "\nConnection lost" << std::endl;
        if (!cause.empty())
            std::cout << "\tcause: " << cause << std::endl;

        std::cout << "Reconnecting..." << std::endl;
        nretry_ = 0;
        attempt_reconnect();
    }

    void attempt_reconnect()
    {
        std::cout << "reconnecting" << std::endl;
        std::this_thread::sleep_for(std::chrono::milliseconds(2500));
        try
        {
            connect(connOpts_);
        }
        catch (const mqtt::exception &exc)
        {
            std::cerr << "Error: " << exc.what() << std::endl;
            exit(1);
        }
    }
};

void Topic::register_callback(Proxy &proxy)
{
    if (!subtopic.empty())
    {
        proxy.register_topic_handler(subtopic, callback_method, &sub_validator, &sub_schema);
        std::cout << "Registered callback for topic: " << subtopic << std::endl;
    }
}